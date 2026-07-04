"""Entry point: wires config -> engine -> activation mode -> keyboard.

Run with:
    python -m src.main --config config.yaml
"""
import argparse
import logging
import sys
import time

from .activation.modes import AlwaysOnActivation, PushToTalkActivation, WakeWordActivation
from .audio.capture import AudioCapture
from .command_matcher import CommandMatcher
from .config import AppConfig, load_config
from .input.keyboard import KeyboardController
from .recognition.base import RecognitionEngine
from .recognition.vosk_engine import VoskEngine

logger = logging.getLogger("main")


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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Speech-to-keyboard for closed-set voice commands.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config(args.config)
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

    activation = build_activation(config, engine, matcher, audio)

    logger.info("Ready. engine=%s activation=%s", config.engine, config.activation.mode)
    logger.info("Commands: %s", {c.name: c.phrases for c in config.commands})

    try:
        activation.run_forever(on_command)
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    finally:
        engine.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
