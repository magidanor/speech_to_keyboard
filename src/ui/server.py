"""Local web UI for editing the closed-set command list and testing phrases
-- typed or spoken, including longer multi-word sentences like "under the
tree" -- against the live recognizer, without hand-editing config.yaml or
running the full src/main.py loop.

Run with:
    python -m src.ui.server        # or just ./commands_config.sh
Then open http://127.0.0.1:5000

Testing always uses the Vosk engine (regardless of `engine:` in config.yaml)
since it can test arbitrary typed/spoken phrases against a grammar built on
the fly -- Rhino's intents are fixed at context-compile time, so it can't be
probed with ad hoc phrases the same way.
"""
import argparse
import logging
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
from ..recognition.base import RecognitionResult
from ..recognition.vosk_engine import VoskEngine

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = Flask(__name__, static_folder=None)

_yaml = YAML()
_yaml.preserve_quotes = True

_state: Dict[str, Any] = {
    "config_path": "config.yaml",
    "engine": None,  # VoskEngine, created in create_app()
    "test_lock": threading.Lock(),
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

    lock: threading.Lock = _state["test_lock"]
    if not lock.acquire(blocking=False):
        return jsonify({"error": "A test is already in progress"}), 409

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
        lock.release()


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
    parser = argparse.ArgumentParser(description="Web UI for editing/testing voice commands.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    create_app(args.config)
    print(f"Open http://{args.host}:{args.port} in your browser.")
    app.run(host=args.host, port=args.port, debug=False, threaded=False)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
