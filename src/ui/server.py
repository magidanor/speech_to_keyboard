"""Local web app: one program with a Run tab (start/stop the actual
speech-to-keyboard pipeline) and a Config tab (edit the closed-set command
list, test phrases -- typed or spoken, including longer multi-word sentences
like "under the tree" -- against the live recognizer).

Run with:
    python -m src.ui.server        # or just ./app.sh
Then open http://127.0.0.1:8765

The Run tab starts src.main.run() in a background thread rather than
shelling out to a second process, so start/stop and live activity logging
are just API calls against this same server. A Quit control (POST
/api/quit) stops the pipeline and terminates the whole server process --
the intended way to close the app when it's launched via a double-click
launcher with no terminal to Ctrl+C.

Phrase testing always uses the Vosk engine (regardless of `engine:` in
config.yaml) since it can test arbitrary typed/spoken phrases against a
grammar built on the fly -- Rhino's intents are fixed at context-compile
time, so it can't be probed with ad hoc phrases the same way. Testing and
the live Run pipeline both need exclusive access to the microphone, so only
one of them can be active at a time (enforced server-side).
"""
import argparse
import collections
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory
from ruamel.yaml import YAML

from ..audio.capture import AudioCapture
from ..command_matcher import CommandMatcher
from ..config import CommandConfig, load_config
from ..main import run as run_pipeline
from ..recognition.base import RecognitionResult
from ..recognition.vosk_engine import VoskEngine

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = Flask(__name__, static_folder=None)

_yaml = YAML()
_yaml.preserve_quotes = True

_state: Dict[str, Any] = {
    "config_path": "config.yaml",
    "engine": None,  # VoskEngine used for testing, created in create_app()
    "mic_owner": None,  # None | "test" | "run" -- who currently holds the mic
    "mic_owner_lock": threading.Lock(),
    "run_thread": None,
    "run_stop_event": None,
    "run_status": "stopped",  # "stopped" | "running" | "stopping"
    "run_error": None,
    "run_log": collections.deque(maxlen=200),
}


def _config_path() -> Path:
    return Path(_state["config_path"]).resolve()


def _load_raw_yaml():
    with _config_path().open("r") as f:
        return _yaml.load(f)


def _save_raw_yaml(data) -> None:
    with _config_path().open("w") as f:
        _yaml.dump(data, f)


def _command_to_dict(cmd: CommandConfig) -> Dict[str, Any]:
    return {
        "name": cmd.name,
        "phrases": list(cmd.phrases),
        "rhino_intent": cmd.rhino_intent or "",
        "key": cmd.key,
    }


def _validate_commands(raw_commands: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_commands, list) or not raw_commands:
        raise ValueError("commands must be a non-empty list")

    cleaned = []
    seen_names = set()
    for i, item in enumerate(raw_commands):
        if not isinstance(item, dict):
            raise ValueError(f"command #{i + 1} must be an object")

        name = str(item.get("name", "")).strip()
        key = str(item.get("key", "")).strip()
        if not name:
            raise ValueError(f"command #{i + 1} is missing a name")
        if not key:
            raise ValueError(f"command '{name}' is missing a key")
        if name in seen_names:
            raise ValueError(f"duplicate command name: {name}")
        seen_names.add(name)

        phrases = [p.strip() for p in item.get("phrases", []) if str(p).strip()]
        rhino_intent = str(item.get("rhino_intent", "") or "").strip()

        if not phrases and not rhino_intent:
            raise ValueError(f"command '{name}' needs at least one phrase or a rhino_intent")

        cleaned.append(
            {
                "name": name,
                "phrases": phrases,
                "rhino_intent": rhino_intent or None,
                "key": key,
            }
        )
    return cleaned


def _commands_from_payload(payload: Dict[str, Any]) -> List[CommandConfig]:
    """Builds CommandConfig objects from a draft list in the request body
    (so edits can be tested before saving), falling back to whatever is
    currently saved in config.yaml if no draft was given.
    """
    raw = payload.get("commands")
    if raw is not None:
        cleaned = _validate_commands(raw)
        return [CommandConfig(**c) for c in cleaned]
    return load_config(str(_config_path())).commands


# --- Microphone arbitration -------------------------------------------------
# The phrase tester and the live Run pipeline both need the mic; only one may
# hold it at a time.


def _try_claim_mic(owner: str) -> bool:
    with _state["mic_owner_lock"]:
        if _state["mic_owner"] is not None:
            return False
        _state["mic_owner"] = owner
        return True


def _release_mic(owner: str) -> None:
    with _state["mic_owner_lock"]:
        if _state["mic_owner"] == owner:
            _state["mic_owner"] = None


def _mic_busy_message() -> str:
    owner = _state["mic_owner"]
    if owner == "run":
        return "Recognition is currently running -- stop it first."
    if owner == "test":
        return "A phrase test is already in progress."
    return "The microphone is in use."


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/commands")
def get_commands():
    config = load_config(str(_config_path()))
    return jsonify(
        {
            "commands": [_command_to_dict(c) for c in config.commands],
            "engine": config.engine,
            "activation_mode": config.activation.mode,
            "vosk_model_path": config.vosk.model_path,
        }
    )


@app.post("/api/commands")
def save_commands():
    payload = request.get_json(force=True) or {}
    try:
        cleaned = _validate_commands(payload.get("commands"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    data = _load_raw_yaml()
    to_write = []
    for c in cleaned:
        entry = {"name": c["name"], "phrases": c["phrases"]}
        if c["rhino_intent"]:
            entry["rhino_intent"] = c["rhino_intent"]
        entry["key"] = c["key"]
        to_write.append(entry)
    data["commands"] = to_write
    _save_raw_yaml(data)

    engine = _state.get("engine")
    if engine is not None:
        matcher = CommandMatcher([CommandConfig(**c) for c in cleaned])
        engine.set_active_grammar(matcher.all_phrases())

    return jsonify({"ok": True, "commands": cleaned})


@app.post("/api/test/text")
def test_text():
    payload = request.get_json(force=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        commands = _commands_from_payload(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    matcher = CommandMatcher(commands, cooldown_seconds=0.0)
    result = RecognitionResult(is_final=True, text=text)
    command = matcher.match(result)

    return jsonify(
        {
            "normalized": text.lower().strip(),
            "matched": _command_to_dict(command) if command else None,
        }
    )


@app.post("/api/test/audio")
def test_audio():
    payload = request.get_json(force=True) or {}
    timeout_seconds = float(payload.get("timeout_seconds", 6.0))

    try:
        commands = _commands_from_payload(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    engine = _state.get("engine")
    if engine is None:
        return jsonify({"error": "Vosk engine is not loaded on the server"}), 500

    if not _try_claim_mic("test"):
        return jsonify({"error": _mic_busy_message()}), 409

    try:
        matcher = CommandMatcher(commands, cooldown_seconds=0.0)
        engine.set_active_grammar(matcher.all_phrases())

        heard_text: Optional[str] = None
        deadline = time.monotonic() + timeout_seconds
        buffer = bytearray()
        frame_bytes = engine.preferred_frame_bytes

        with AudioCapture(sample_rate=engine.sample_rate) as audio:
            while time.monotonic() < deadline and heard_text is None:
                remaining = deadline - time.monotonic()
                try:
                    buffer.extend(audio.read(timeout=max(remaining, 0.01)))
                except queue.Empty:
                    break
                while len(buffer) >= frame_bytes:
                    frame, buffer = bytes(buffer[:frame_bytes]), buffer[frame_bytes:]
                    result = engine.feed_audio(frame)
                    if result is not None and result.is_final and result.text:
                        heard_text = result.text
                        break

            if heard_text is None:
                flushed = engine.flush()
                if flushed is not None and flushed.text:
                    heard_text = flushed.text

        command = None
        if heard_text:
            command = matcher.match(RecognitionResult(is_final=True, text=heard_text))

        return jsonify(
            {
                "heard_text": heard_text,
                "matched": _command_to_dict(command) if command else None,
                "timed_out": heard_text is None,
            }
        )
    finally:
        # Restore the grammar to whatever's actually saved on disk, so a
        # draft test doesn't leave the shared engine out of sync.
        saved_matcher = CommandMatcher(load_config(str(_config_path())).commands)
        engine.set_active_grammar(saved_matcher.all_phrases())
        _release_mic("test")


# --- Run control: starts/stops the actual voice-to-keyboard pipeline -------


def _run_target(config_path: str, stop_event: threading.Event) -> None:
    def hook(command, result, latency_ms):
        heard = result.text or result.intent
        _state["run_log"].append(
            f"{time.strftime('%H:%M:%S')}  heard {heard!r} -> {command.name} "
            f"(key={command.key}, {latency_ms:.0f}ms)"
        )

    try:
        run_pipeline(config_path=config_path, stop_event=stop_event, on_command_hook=hook)
    except Exception as exc:
        logger.exception("Voice pipeline crashed")
        _state["run_error"] = str(exc)
    finally:
        _state["run_status"] = "stopped"
        _release_mic("run")


@app.post("/api/run/start")
def start_run():
    if _state["run_status"] == "running":
        return jsonify({"error": "Already running"}), 409
    if not _try_claim_mic("run"):
        return jsonify({"error": _mic_busy_message()}), 409

    try:
        # Fail fast on an obviously broken config before spinning up the
        # thread (e.g. bad engine name, missing Rhino context path).
        load_config(_state["config_path"])
    except Exception as exc:
        _release_mic("run")
        return jsonify({"error": f"Invalid config.yaml: {exc}"}), 400

    _state["run_error"] = None
    _state["run_log"].clear()
    stop_event = threading.Event()
    _state["run_stop_event"] = stop_event

    thread = threading.Thread(
        target=_run_target, args=(_state["config_path"], stop_event), daemon=True
    )
    _state["run_thread"] = thread
    _state["run_status"] = "running"
    thread.start()
    return jsonify({"ok": True})


@app.post("/api/run/stop")
def stop_run():
    if _state["run_status"] not in ("running", "stopping"):
        return jsonify({"error": "Not running"}), 409
    stop_event: Optional[threading.Event] = _state.get("run_stop_event")
    if stop_event is not None:
        stop_event.set()
    _state["run_status"] = "stopping"
    return jsonify({"ok": True})


@app.get("/api/run/status")
def run_status():
    thread: Optional[threading.Thread] = _state.get("run_thread")
    if thread is not None and not thread.is_alive() and _state["run_status"] in ("running", "stopping"):
        _state["run_status"] = "stopped"
    return jsonify(
        {
            "status": _state["run_status"],
            "log": list(_state["run_log"])[-50:],
            "error": _state["run_error"],
        }
    )


@app.post("/api/quit")
def quit_app():
    """Shuts down the whole app -- the point of this endpoint is to give
    non-technical users (running via a double-click launcher, with no
    terminal to Ctrl+C) a way to close the program from inside it.
    """
    stop_event: Optional[threading.Event] = _state.get("run_stop_event")
    if _state["run_status"] in ("running", "stopping") and stop_event is not None:
        stop_event.set()
        thread: Optional[threading.Thread] = _state.get("run_thread")
        if thread is not None:
            thread.join(timeout=5.0)

    # Reply before the process disappears out from under this request.
    threading.Timer(0.3, lambda: os._exit(0)).start()
    return jsonify({"ok": True})


def create_app(config_path: str = "config.yaml") -> Flask:
    _state["config_path"] = config_path
    config = load_config(config_path)
    logger.info("Loading Vosk model from %s ...", config.vosk.model_path)
    engine = VoskEngine(model_path=config.vosk.model_path, sample_rate=config.vosk.sample_rate)
    matcher = CommandMatcher(config.commands)
    engine.set_active_grammar(matcher.all_phrases())
    _state["engine"] = engine
    logger.info("Model loaded, ready.")
    return app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Speech-to-keyboard: run control + command editor web app.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Also log each HTTP request (noisy: the UI polls once a second)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    # The frontend polls /api/run/status once a second; Werkzeug's dev server
    # logs every request at INFO by default, which drowns out anything else
    # in the terminal. Keep that quiet unless explicitly asked for.
    logging.getLogger("werkzeug").setLevel(logging.INFO if args.verbose else logging.WARNING)

    create_app(args.config)
    print(f"Open http://{args.host}:{args.port} in your browser.")
    # threaded=True: status polling and other API calls shouldn't block behind
    # a long-running phrase test or the live Run pipeline (which runs in its
    # own background thread, not a Flask request thread, but status/stop
    # requests still need to be served promptly while it's active).
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
