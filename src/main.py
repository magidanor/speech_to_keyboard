"""Core speech-to-keyboard pipeline: config -> engine -> activation mode ->
keyboard. `run()` is the shared entry point into that pipeline, used both by
the CLI below and by src/ui/server.py's Run tab, which executes it in a
background thread with a stop_event so it can be started and stopped from
the web app instead of a second process.

CLI usage:
    python -m src.main --config config.yaml
"""
import argparse
import logging
import sys
import threading
import time
from typing import Callable, Optional

from .activation.modes import AlwaysOnActivation, PushToTalkActivation, WakeWordActivation
from .audio.capture import AudioCapture
from .command_matcher import CommandMatcher
from .config import AppConfig, CommandConfig, load_config
from .input.keyboard import KeyboardController
from .recognition.base import RecognitionEngine, RecognitionResult
from .recognition.vosk_engine import VoskEngine

logger = logging.getLogger("main")

OnCommandHook = Callable[[CommandConfig, RecognitionResult, float], None]


def build_engine(config: AppConfig) -> RecognitionEngine:
    if config.engine == "vosk":
        return VoskEngine(model_path=config.vosk.model_path, sample_rate=config.vosk.sample_rate)
    if config.engine == "rhino":
        from .recognition.rhino_engine import RhinoEngine

        return RhinoEngine(
            access_key=config.rhino.access_key,
            context_path=config.rhino.context_path,
            sensitivity=config.rhino.sensitivity,
        )
    raise ValueError(f"Unknown engine: {config.engine!r}")


def build_activation(config: AppConfig, engine, matcher, audio):
    mode = config.activation.mode
    if mode == "always_on":
        return AlwaysOnActivation(engine, matcher, audio)
    if mode == "push_to_talk":
        return PushToTalkActivation(engine, matcher, audio, hotkey=config.activation.push_to_talk_key)
    if mode == "wake_word":
        return WakeWordActivation(
            engine,
            matcher,
            audio,
            wake_word=config.activation.wake_word,
            wake_window_seconds=config.activation.wake_window_seconds,
        )
    raise ValueError(f"Unknown activation mode: {mode!r}")


def run(
    config_path: str = "config.yaml",
    stop_event: Optional[threading.Event] = None,
    on_command_hook: Optional[OnCommandHook] = None,
) -> None:
    """Runs the speech-to-keyboard pipeline until `stop_event` is set (or
    forever, if no stop_event is given -- e.g. plain CLI usage, stopped with
    Ctrl+C instead).
    """
    config = load_config(config_path)
    matcher = CommandMatcher(config.commands, cooldown_seconds=config.matching.cooldown_seconds)
    engine = build_engine(config)

    # For Vosk, constrain the recognizer to the command grammar up front --
    # unless we're in wake_word mode, where WakeWordActivation manages the
    # grammar itself (starting with just the wake word).
    if config.engine == "vosk" and config.activation.mode != "wake_word":
        engine.set_active_grammar(matcher.all_phrases())

    keyboard = KeyboardController()
    audio = AudioCapture(sample_rate=engine.sample_rate)

    def on_command(command, result):
        heard = result.text or result.intent
        dispatch_latency_ms = (time.monotonic() - result.timestamp) * 1000
        keyboard.tap(command.key, duration=config.matching.key_press_duration)
        logger.info(
            "Heard %r -> command %r -> key %r | recognition-to-dispatch: %.1fms",
            heard,
            command.name,
            command.key,
            dispatch_latency_ms,
        )
        if on_command_hook is not None:
            on_command_hook(command, result, dispatch_latency_ms)

    activation = build_activation(config, engine, matcher, audio)

    logger.info("Ready. engine=%s activation=%s", config.engine, config.activation.mode)
    logger.info("Commands: %s", {c.name: c.phrases for c in config.commands})

    try:
        activation.run_forever(on_command, stop_event=stop_event)
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    finally:
        engine.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Speech-to-keyboard for closed-set voice commands.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run(config_path=args.config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
