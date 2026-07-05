"""Offline, grammar-constrained recognition using Vosk.

Constraining the recognizer to a fixed JSON grammar (the closed set of
command phrases) both speeds up decoding and reduces misrecognitions, since
the decoder only has to choose among a handful of outcomes instead of an
open vocabulary. "[unk]" is added to every grammar so out-of-set speech is
classified as unknown rather than force-matched to the nearest command.

Vosk does its own endpointing: `AcceptWaveform` returns True once it detects
the utterance is finished (via internal silence detection), which is what
makes "always listening" mode possible without a separate VAD.
"""
import json
import logging
from typing import Iterable, Optional

from vosk import KaldiRecognizer, Model

from .base import RecognitionEngine, RecognitionResult

logger = logging.getLogger(__name__)


class VoskEngine(RecognitionEngine):
    def __init__(
        self,
        model_path: str,
        sample_rate: int = 16000,
        phrases: Optional[Iterable[str]] = None,
    ):
        self.sample_rate = sample_rate
        # ~250ms chunks of 16-bit mono audio. Vosk doesn't require a strict
        # frame size, but smaller chunks trade a little CPU overhead for
        # faster partial results.
        self.preferred_frame_bytes = int(sample_rate * 0.25) * 2

        self._model = Model(model_path)
        self._phrases = list(phrases) if phrases else None
        self._recognizer = self._make_recognizer(self._phrases)

    def _make_recognizer(self, phrases: Optional[Iterable[str]]) -> KaldiRecognizer:
        if phrases:
            grammar = json.dumps(list(phrases) + ["[unk]"])
            recognizer = KaldiRecognizer(self._model, self.sample_rate, grammar)
        else:
            recognizer = KaldiRecognizer(self._model, self.sample_rate)
        return recognizer

    def set_active_grammar(self, phrases: Optional[Iterable[str]]) -> None:
        """Rebuild the recognizer with a new phrase list. Recreating a
        KaldiRecognizer is cheap (the heavy acoustic model lives in `Model`
        and is shared), so this is fine to call on every wake-word cycle.
        """
        self._phrases = list(phrases) if phrases else None
        self._recognizer = self._make_recognizer(self._phrases)

    def feed_audio(self, frame_bytes: bytes) -> Optional[RecognitionResult]:
        if self._recognizer.AcceptWaveform(frame_bytes):
            text = json.loads(self._recognizer.Result()).get("text", "").strip()
            if not text:
                return None
            return RecognitionResult(is_final=True, text=text)

        # Partial results are useful for on-screen/debug feedback but should
        # not be used to trigger commands - only act on is_final results.
        partial = json.loads(self._recognizer.PartialResult()).get("partial", "").strip()
        if partial:
            return RecognitionResult(is_final=False, text=partial)
        return None

    def flush(self) -> Optional[RecognitionResult]:
        text = json.loads(self._recognizer.FinalResult()).get("text", "").strip()
        if not text:
            return None
        return RecognitionResult(is_final=True, text=text)
