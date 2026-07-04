"""Three ways to decide when audio should be fed to the recognizer.

- AlwaysOnActivation: continuously streams the mic. Relies on the engine's
  own endpointing (silence detection) to decide when an utterance ends, so
  no separate VAD library is needed. This is the default.
- PushToTalkActivation: only feeds audio while a hotkey is held. Lowest
  complexity, zero false triggers, and typically the lowest *perceived*
  latency since there's no silence-timeout to wait out.
- WakeWordActivation: listens for a wake word with a tiny grammar, then
  temporarily switches to the full command grammar. Currently requires an
  engine that supports `set_active_grammar` (VoskEngine).

All three accept an optional `stop_event` in `run_forever()` so a caller
(e.g. the web UI, running this in a background thread) can ask the loop to
exit cleanly -- each polls the mic with a short timeout instead of blocking
forever so the stop request is noticed promptly.
"""
import logging
import queue
import threading
import time
from typing import Callable, Optional

from ..audio.capture import AudioCapture
from ..command_matcher import CommandMatcher
from ..config import CommandConfig
from ..recognition.base import RecognitionEngine, RecognitionResult

logger = logging.getLogger(__name__)

OnCommand = Callable[[CommandConfig, RecognitionResult], None]

# How often the mic-read loops wake up to check for a stop request.
_POLL_INTERVAL = 0.5


def _should_stop(stop_event: Optional[threading.Event]) -> bool:
    return stop_event is not None and stop_event.is_set()


def _dispatch(result: Optional[RecognitionResult], matcher: CommandMatcher, on_command: OnCommand) -> None:
    if result is None or not result.is_final:
        return
    command = matcher.match(result)
    if command is not None:
        on_command(command, result)
    elif result.text:
        logger.debug("No command matched for: %r", result.text)


class AlwaysOnActivation:
    def __init__(self, engine: RecognitionEngine, matcher: CommandMatcher, audio: AudioCapture):
        self._engine = engine
        self._matcher = matcher
        self._audio = audio

    def run_forever(self, on_command: OnCommand, stop_event: Optional[threading.Event] = None) -> None:
        buffer = bytearray()
        frame_bytes = self._engine.preferred_frame_bytes
        with self._audio:
            while not _should_stop(stop_event):
                try:
                    buffer.extend(self._audio.read(timeout=_POLL_INTERVAL))
                except queue.Empty:
                    continue
                while len(buffer) >= frame_bytes:
                    frame, buffer = bytes(buffer[:frame_bytes]), buffer[frame_bytes:]
                    result = self._engine.feed_audio(frame)
                    _dispatch(result, self._matcher, on_command)


class PushToTalkActivation:
    def __init__(
        self,
        engine: RecognitionEngine,
        matcher: CommandMatcher,
        audio: AudioCapture,
        hotkey: str = "ctrl_r",
    ):
        self._engine = engine
        self._matcher = matcher
        self._audio = audio
        self._hotkey = hotkey
        self._listening = False

    def run_forever(self, on_command: OnCommand, stop_event: Optional[threading.Event] = None) -> None:
        from pynput import keyboard as pynput_keyboard

        target_key = self._resolve_key(pynput_keyboard, self._hotkey)
        buffer = bytearray()
        frame_bytes = self._engine.preferred_frame_bytes

        def on_press(key):
            if key == target_key and not self._listening:
                self._listening = True
                buffer.clear()
                logger.info("Listening...")

        def on_release(key):
            if key == target_key and self._listening:
                self._listening = False
                logger.info("Stopped listening, finalizing...")
                result = self._engine.flush()
                _dispatch(result, self._matcher, on_command)

        listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

        try:
            with self._audio:
                while not _should_stop(stop_event):
                    try:
                        chunk = self._audio.read(timeout=_POLL_INTERVAL)
                    except queue.Empty:
                        continue
                    if not self._listening:
                        continue
                    buffer.extend(chunk)
                    while len(buffer) >= frame_bytes:
                        frame, buffer = bytes(buffer[:frame_bytes]), buffer[frame_bytes:]
                        result = self._engine.feed_audio(frame)
                        _dispatch(result, self._matcher, on_command)
        finally:
            listener.stop()

    @staticmethod
    def _resolve_key(pynput_keyboard, name: str):
        name = name.lower()
        if hasattr(pynput_keyboard.Key, name):
            return getattr(pynput_keyboard.Key, name)
        return pynput_keyboard.KeyCode.from_char(name)


class WakeWordActivation:
    def __init__(
        self,
        engine: RecognitionEngine,
        matcher: CommandMatcher,
        audio: AudioCapture,
        wake_word: str,
        wake_window_seconds: float = 4.0,
    ):
        if not hasattr(engine, "set_active_grammar"):
            raise NotImplementedError(
                "WakeWordActivation requires an engine that supports "
                "set_active_grammar (currently only VoskEngine)."
            )
        self._engine = engine
        self._matcher = matcher
        self._audio = audio
        self._wake_word = wake_word.lower()
        self._wake_window = wake_window_seconds
        self._command_phrases = matcher.all_phrases()

    def run_forever(self, on_command: OnCommand, stop_event: Optional[threading.Event] = None) -> None:
        buffer = bytearray()
        self._engine.set_active_grammar([self._wake_word])
        listening_for_command_until = 0.0

        with self._audio:
            while not _should_stop(stop_event):
                try:
                    buffer.extend(self._audio.read(timeout=_POLL_INTERVAL))
                except queue.Empty:
                    continue
                frame_bytes = self._engine.preferred_frame_bytes
                while len(buffer) >= frame_bytes:
                    frame, buffer = bytes(buffer[:frame_bytes]), buffer[frame_bytes:]
                    result = self._engine.feed_audio(frame)
                    if result is None or not result.is_final:
                        continue

                    now = time.monotonic()
                    if now >= listening_for_command_until:
                        # Currently listening for the wake word.
                        if self._wake_word in (result.text or ""):
                            logger.info("Wake word detected, listening for a command...")
                            self._engine.set_active_grammar(self._command_phrases)
                            listening_for_command_until = now + self._wake_window
                        continue

                    # Currently within the command window.
                    command = self._matcher.match(result)
                    if command is not None:
                        on_command(command, result)
                    self._engine.set_active_grammar([self._wake_word])
                    listening_for_command_until = 0.0
