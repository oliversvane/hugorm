from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class AudioChunk:
    pcm: np.ndarray
    start: float
    end: float


class FixedWindowChunker:
    """
    Cuts an incoming PCM stream into overlapping fixed-duration windows for ASR.

    The overlap lets a later window refine word boundaries and catch words that
    were cut by the previous window boundary — downstream consumers replace
    earlier words in the overlap region with words from the newer window.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        window_s: float = 5.0,
        overlap_s: float = 0.5,
    ) -> None:
        if overlap_s >= window_s:
            raise ValueError("overlap must be smaller than window")
        self.sample_rate = sample_rate
        self.window_samples = int(window_s * sample_rate)
        self.overlap_samples = int(overlap_s * sample_rate)
        self._step = self.window_samples - self.overlap_samples
        self._buf: np.ndarray = np.zeros(0, dtype=np.float32)
        self._window_start_samples = 0

    def push(self, pcm: np.ndarray) -> list[AudioChunk]:
        pcm = np.asarray(pcm, dtype=np.float32).reshape(-1)
        if pcm.size:
            self._buf = np.concatenate([self._buf, pcm])
        out: list[AudioChunk] = []
        while len(self._buf) >= self.window_samples:
            chunk_pcm = self._buf[: self.window_samples].copy()
            start = self._window_start_samples / self.sample_rate
            end = (self._window_start_samples + self.window_samples) / self.sample_rate
            out.append(AudioChunk(pcm=chunk_pcm, start=start, end=end))
            self._buf = self._buf[self._step :]
            self._window_start_samples += self._step
        return out

    def flush(self) -> list[AudioChunk]:
        if len(self._buf) == 0:
            return []
        start = self._window_start_samples / self.sample_rate
        end = (self._window_start_samples + len(self._buf)) / self.sample_rate
        chunk = AudioChunk(pcm=self._buf.copy(), start=start, end=end)
        self._window_start_samples += len(self._buf)
        self._buf = np.zeros(0, dtype=np.float32)
        return [chunk]
