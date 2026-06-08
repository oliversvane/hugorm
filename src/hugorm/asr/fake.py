from __future__ import annotations

import asyncio
from collections.abc import Callable

import numpy as np

from .base import ASRResult, ASRWord


class FakeASR:
    """Deterministic ASR used for tests. Emits synthetic words per chunk."""

    sample_rate = 16000

    def __init__(
        self,
        words_per_chunk: int = 3,
        text_fn: Callable[[int], str] | None = None,
        latency: float = 0.0,
    ) -> None:
        self._words_per_chunk = words_per_chunk
        self._text_fn = text_fn or (lambda i: f"word{i}")
        self._latency = latency
        self._counter = 0

    async def transcribe(
        self,
        pcm: np.ndarray,
        chunk_start: float,
        language: str | None = None,
    ) -> ASRResult:
        if self._latency:
            await asyncio.sleep(self._latency)
        duration = len(pcm) / self.sample_rate
        n = self._words_per_chunk
        per = duration / max(n, 1)
        words: list[ASRWord] = []
        for i in range(n):
            s = chunk_start + i * per
            e = s + per * 0.9
            words.append(
                ASRWord(text=self._text_fn(self._counter), start=s, end=e, confidence=0.9)
            )
            self._counter += 1
        return ASRResult(words=words, language=language or "en")

    async def close(self) -> None:
        return None
