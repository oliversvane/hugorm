from __future__ import annotations

import asyncio
import logging

import numpy as np

from .base import ASRResult, ASRWord

logger = logging.getLogger(__name__)


class FasterWhisperBackend:
    """faster-whisper implementation of the ASRBackend protocol."""

    sample_rate = 16000

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
    ) -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._beam_size = beam_size

    async def transcribe(
        self,
        pcm: np.ndarray,
        chunk_start: float,
        language: str | None = None,
    ) -> ASRResult:
        return await asyncio.to_thread(self._transcribe_sync, pcm, chunk_start, language)

    def _transcribe_sync(
        self, pcm: np.ndarray, chunk_start: float, language: str | None
    ) -> ASRResult:
        segments, info = self._model.transcribe(
            pcm,
            language=language,
            task="transcribe",
            beam_size=self._beam_size,
            word_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        words: list[ASRWord] = []
        for seg in segments:
            if not seg.words:
                continue
            for w in seg.words:
                text = w.word.strip()
                if not text:
                    continue
                words.append(
                    ASRWord(
                        text=text,
                        start=chunk_start + float(w.start),
                        end=chunk_start + float(w.end),
                        confidence=float(w.probability) if w.probability is not None else None,
                    )
                )
        return ASRResult(words=words, language=info.language)

    async def close(self) -> None:
        return None
