"""Common interface all recognition engines implement.

Two very different engines are supported:

- VoskEngine: general-purpose STT constrained to a closed grammar. Produces
  free-text transcripts (`result.text`).
- RhinoEngine: a speech-to-intent engine that skips transcription entirely
  and maps audio directly to an intent name (`result.intent`).

`CommandMatcher` (see src/command_matcher.py) knows how to handle either.
"""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class RecognitionResult:
    is_final: bool
    text: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    # Stamped at creation time so callers can measure recognition-to-action
    # latency without plumbing timestamps through every layer.
    timestamp: float = field(default_factory=time.monotonic)


class RecognitionEngine(ABC):
    sample_rate: int = 16000
    # How many bytes of 16-bit mono PCM audio `feed_audio` expects per call.
    # Callers (activation modes) buffer microphone audio and slice it into
    # chunks of exactly this size before feeding it in.
    preferred_frame_bytes: int = 4000

    @abstractmethod
    def feed_audio(self, frame_bytes: bytes) -> Optional[RecognitionResult]:
        """Feed one frame of audio. Returns a result if one is available."""
        raise NotImplementedError

    def set_active_grammar(self, phrases: Iterable[str]) -> None:
        """Swap the active phrase list at runtime (e.g. wake-word activation
        switching between a wake-word grammar and the full command grammar).
        Only engines that support this (currently VoskEngine) implement it.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support dynamic grammar switching"
        )

    def flush(self) -> Optional[RecognitionResult]:
        """Force-finalize any buffered audio, e.g. on push-to-talk key release."""
        return None

    def close(self) -> None:
        pass
