from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass
class ASRWord:
    text: str
    start: float
    end: float
    confidence: float | None = None


@dataclass
class ASRResult:
    words: list[ASRWord] = field(default_factory=list)
    language: str | None = None


@runtime_checkable
class ASRBackend(Protocol):
    """
    Pluggable ASR. `transcribe` is called once per audio chunk; the implementation
    is responsible for returning word-level timestamps in absolute session time
    (i.e. `chunk_start + word_offset_within_chunk`).
    """

    sample_rate: int

    async def transcribe(
        self,
        pcm: np.ndarray,
        chunk_start: float,
        language: str | None = None,
    ) -> ASRResult: ...

    async def close(self) -> None: ...
