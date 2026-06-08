from __future__ import annotations

import asyncio
from collections.abc import Awaitable

import numpy as np
import pytest

from hugorm.asr.fake import FakeASR
from hugorm.events import (
    SegmentFinalized,
    SessionEnded,
    SessionStarted,
    TranscriptEvent,
    WordsUpserted,
)
from hugorm.pipeline.session import SessionConfig, TranscriptionSession


class Collector:
    def __init__(self) -> None:
        self.events: list[TranscriptEvent] = []

    async def __call__(self, event: TranscriptEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_session_emits_start_words_and_end_in_order():
    asr = FakeASR(words_per_chunk=2)
    emit = Collector()
    cfg = SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0)
    session = TranscriptionSession(asr=asr, diarizer=None, emit=emit, config=cfg)

    await session.start()
    for _ in range(3):
        await session.push_pcm(np.zeros(16000, dtype=np.float32))
    await session.close()

    types = [type(e).__name__ for e in emit.events]
    assert types[0] == "SessionStarted"
    assert types[-1] == "SessionEnded"
    assert "WordsUpserted" in types
    assert [e.seq for e in emit.events] == list(range(1, len(emit.events) + 1))


@pytest.mark.asyncio
async def test_session_without_audio_still_closes_cleanly():
    asr = FakeASR()
    emit = Collector()
    session = TranscriptionSession(asr=asr, diarizer=None, emit=emit)

    await session.start()
    await session.close()

    assert isinstance(emit.events[0], SessionStarted)
    assert isinstance(emit.events[-1], SessionEnded)
    assert any(isinstance(e, SegmentFinalized) for e in emit.events)


@pytest.mark.asyncio
async def test_words_carry_absolute_timestamps():
    asr = FakeASR(words_per_chunk=2)
    emit = Collector()
    cfg = SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0)
    session = TranscriptionSession(asr=asr, diarizer=None, emit=emit, config=cfg)

    await session.start()
    await session.push_pcm(np.zeros(16000 * 2, dtype=np.float32))
    await session.close()

    upserts = [e for e in emit.events if isinstance(e, WordsUpserted)]
    assert len(upserts) >= 2
    second = upserts[1]
    assert second.window_start >= 1.0
    for w in second.words:
        assert w.start >= 1.0
