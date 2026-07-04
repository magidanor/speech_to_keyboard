"""Microphone streaming, decoupled from whichever recognition engine consumes it."""
import logging
import queue
from typing import Optional

import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioCapture:
    """Streams the microphone as raw 16-bit mono PCM chunks.

    Use as a context manager:

        with AudioCapture(sample_rate=16000) as audio:
            while True:
                chunk = audio.read()
                ...
    """

    def __init__(self, sample_rate: int = 16000, blocksize: int = 2000, device: Optional[int] = None):
        self.sample_rate = sample_rate
        self._queue: "queue.Queue[bytes]" = queue.Queue()
        self._stream = sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=blocksize,
            dtype="int16",
            channels=1,
            device=device,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        if status:
            # e.g. input overflow -- log but keep the audio thread alive.
            logger.warning("Audio input status: %s", status)
        self._queue.put(bytes(indata))

    def __enter__(self) -> "AudioCapture":
        self._stream.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stream.stop()
        self._stream.close()

    def read(self, timeout: Optional[float] = None) -> bytes:
        return self._queue.get(timeout=timeout)
