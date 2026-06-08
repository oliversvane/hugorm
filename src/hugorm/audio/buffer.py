from __future__ import annotations

import numpy as np


class PCMRingBuffer:
    """
    Append-only view over streamed PCM samples with a bounded history.
    Older samples are dropped once `max_seconds` of audio has been retained,
    so diarization can re-process recent context without unbounded memory use.
    """

    def __init__(self, sample_rate: int, max_seconds: float = 60.0) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self.sample_rate = sample_rate
        self._max = int(max_seconds * sample_rate)
        self._buf: np.ndarray = np.zeros(0, dtype=np.float32)
        self._dropped = 0

    @property
    def total_samples(self) -> int:
        return self._dropped + len(self._buf)

    @property
    def duration(self) -> float:
        return self.total_samples / self.sample_rate

    @property
    def history_start(self) -> float:
        return self._dropped / self.sample_rate

    def append(self, pcm: np.ndarray) -> None:
        pcm = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if pcm.size == 0:
            return
        self._buf = np.concatenate([self._buf, pcm])
        overflow = len(self._buf) - self._max
        if overflow > 0:
            self._dropped += overflow
            self._buf = self._buf[overflow:]

    def slice_seconds(self, start: float, end: float) -> np.ndarray:
        start_s = max(int(start * self.sample_rate), self._dropped)
        end_s = max(int(end * self.sample_rate), self._dropped)
        a = start_s - self._dropped
        b = end_s - self._dropped
        a = max(0, min(a, len(self._buf)))
        b = max(0, min(b, len(self._buf)))
        if b <= a:
            return np.zeros(0, dtype=np.float32)
        return self._buf[a:b].copy()
