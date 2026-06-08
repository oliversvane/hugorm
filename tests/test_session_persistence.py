from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from hugorm.asr.fake import FakeASR
from hugorm.events import RefinedTurn
from hugorm.llm.agent import TurnInput
from hugorm.pipeline.session import SessionConfig, SessionSnapshot, TranscriptionSession


class Collector:
    def __init__(self) -> None:
        self.events = []

    async def __call__(self, event):
        self.events.append(event)


@dataclass
class StubAgent:
    calls: list = field(default_factory=list)

    async def refine(self, turns: list[TurnInput], entities, context=None):  # type: ignore[no-untyped-def]
        self.calls.append(list(turns))
        return [
            RefinedTurn(speaker=t.speaker, start=t.start, end=t.end, text=f"refined: {t.text}")
            for t in turns
        ]


@pytest.mark.asyncio
async def test_on_session_end_receives_snapshot_with_words() -> None:
    asr = FakeASR(words_per_chunk=2)
    emit = Collector()
    captured: list[SessionSnapshot] = []

    async def hook(snapshot: SessionSnapshot) -> None:
        captured.append(snapshot)

    session = TranscriptionSession(
        asr=asr,
        diarizer=None,
        emit=emit,
        on_session_end=hook,
        config=SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0),
    )
    await session.start()
    for _ in range(2):
        await session.push_pcm(np.zeros(16000, dtype=np.float32))
    await session.close()

    assert len(captured) == 1
    snap = captured[0]
    assert snap.session_id == session.session_id
    assert len(snap.words) > 0
    assert snap.started_at <= snap.ended_at


@pytest.mark.asyncio
async def test_snapshot_includes_refined_turns() -> None:
    asr = FakeASR(words_per_chunk=2)
    emit = Collector()
    agent = StubAgent()
    captured: list[SessionSnapshot] = []

    async def hook(snapshot: SessionSnapshot) -> None:
        captured.append(snapshot)

    async def fetch():
        return []

    session = TranscriptionSession(
        asr=asr,
        diarizer=None,
        emit=emit,
        agent=agent,  # type: ignore[arg-type]
        fetch_entities=fetch,
        on_session_end=hook,
        config=SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0),
    )
    await session.start()
    for _ in range(2):
        await session.push_pcm(np.zeros(16000, dtype=np.float32))
    await session.close()

    assert len(captured) == 1
    assert captured[0].refined_turns
    assert all(t.text.startswith("refined: ") for t in captured[0].refined_turns)


@pytest.mark.asyncio
async def test_hook_failure_does_not_block_session_end() -> None:
    asr = FakeASR(words_per_chunk=1)
    emit = Collector()

    async def bad_hook(snapshot: SessionSnapshot) -> None:
        raise RuntimeError("boom")

    session = TranscriptionSession(
        asr=asr,
        diarizer=None,
        emit=emit,
        on_session_end=bad_hook,
        config=SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0),
    )
    await session.start()
    await session.push_pcm(np.zeros(16000, dtype=np.float32))
    await session.close()

    types = [type(e).__name__ for e in emit.events]
    assert types[-1] == "SessionEnded"
