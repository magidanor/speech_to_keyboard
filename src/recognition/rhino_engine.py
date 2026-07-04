"""Picovoice Rhino speech-to-intent engine (optional, opt-in).

Unlike Vosk, Rhino never produces a free-text transcript -- it maps audio
directly to one of the intents defined in a Rhino "context" you design and
compile for free at https://console.picovoice.ai. Because it's a single
end-to-end model rather than a transcribe-then-parse pipeline, it tends to
be the lowest-latency, most accurate option for a small fixed voice-command
set. The tradeoff is needing a (free-tier) Picovoice account and your own
trained context file.

Setup:
  1. pip install pvrhino
  2. Create a free AccessKey at https://console.picovoice.ai
  3. In the console, create a "Speech-to-Intent" context with one intent per
     command (e.g. moveLeft, moveRight, jump, crouch, stop) and matching
     expressions ("left", "go left", etc). Download the .rhn file for your
     platform.
  4. In config.yaml, set engine: rhino and fill in rhino.access_key /
     rhino.context_path.
  5. Make sure each command's `rhino_intent` in config.yaml matches the
     intent name you defined in the console.

Note: wake_word activation mode currently requires an engine that supports
runtime grammar switching (VoskEngine); RhinoEngine intentionally raises in
that case -- see WakeWordActivation in src/activation/modes.py.
"""
import logging
import struct
from typing import Optional

from .base import RecognitionEngine, RecognitionResult

logger = logging.getLogger(__name__)


class RhinoEngine(RecognitionEngine):
    def __init__(self, access_key: str, context_path: str, sensitivity: float = 0.5):
        try:
            import pvrhino
        except ImportError as exc:
            raise ImportError(
                "pvrhino is not installed. Run `pip install pvrhino` to use engine: rhino."
            ) from exc

        if not access_key:
            raise ValueError("rhino.access_key is not set in config.yaml")
        if not context_path:
            raise ValueError("rhino.context_path is not set in config.yaml")

        self._rhino = pvrhino.create(
            access_key=access_key, context_path=context_path, sensitivity=sensitivity
        )
        self.sample_rate = self._rhino.sample_rate
        self.frame_length = self._rhino.frame_length
        # Rhino requires frames of exactly `frame_length` 16-bit samples --
        # unlike Vosk it will not tolerate arbitrary chunk sizes.
        self.preferred_frame_bytes = self.frame_length * 2
        self._unpack_fmt = "<%dh" % self.frame_length

    def feed_audio(self, frame_bytes: bytes) -> Optional[RecognitionResult]:
        pcm = struct.unpack_from(self._unpack_fmt, frame_bytes)
        is_finalized = self._rhino.process(pcm)
        if not is_finalized:
            return None

        inference = self._rhino.get_inference()
        if inference.is_understood:
            return RecognitionResult(is_final=True, intent=inference.intent, confidence=1.0)

        logger.debug("Rhino: speech was not understood (outside the trained context).")
        return RecognitionResult(is_final=True, intent=None)

    def close(self) -> None:
        self._rhino.delete()
