from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass
class DiarSegment:
    start: float
    end: float
    speaker: str


@runtime_checkable
class DiarizationBackend(Protocol):
    sample_rate: int

    async def diarize(
        self,
        pcm: np.ndarray,
        offset: float = 0.0,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> list[DiarSegment]: ...
