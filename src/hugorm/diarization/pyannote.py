from __future__ import annotations

import asyncio
import logging

import numpy as np

from .base import DiarSegment

logger = logging.getLogger(__name__)


class PyannoteDiarizer:
    sample_rate = 16000

    def __init__(
        self,
        model: str = "pyannote/speaker-diarization-3.1",
        hf_token: str | None = None,
        device: str = "auto",
    ) -> None:
        import torch
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(model, token=hf_token)
        if pipeline is None:
            raise RuntimeError(
                f"Failed to load diarization pipeline '{model}'. "
                "Have you accepted its terms on huggingface.co and set HUGORM_HF_TOKEN?"
            )
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        pipeline.to(torch.device(device))
        self._pipeline = pipeline

    async def diarize(
        self,
        pcm: np.ndarray,
        offset: float = 0.0,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> list[DiarSegment]:
        return await asyncio.to_thread(
            self._diarize_sync, pcm, offset, num_speakers, min_speakers, max_speakers
        )

    def _diarize_sync(
        self,
        pcm: np.ndarray,
        offset: float,
        num_speakers: int | None,
        min_speakers: int | None,
        max_speakers: int | None,
    ) -> list[DiarSegment]:
        import torch
        from pyannote.core import Annotation

        waveform = torch.from_numpy(np.ascontiguousarray(pcm, dtype=np.float32)).unsqueeze(0)
        kwargs: dict = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers
        result = self._pipeline(
            {"waveform": waveform, "sample_rate": self.sample_rate}, **kwargs
        )
        annotation: Annotation = getattr(result, "exclusive_speaker_diarization", None) or getattr(
            result, "speaker_diarization", result
        )
        segs: list[DiarSegment] = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            segs.append(
                DiarSegment(
                    start=float(turn.start) + offset,
                    end=float(turn.end) + offset,
                    speaker=str(speaker),
                )
            )
        return segs
