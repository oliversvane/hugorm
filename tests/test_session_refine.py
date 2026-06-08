from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from hugorm.asr.fake import FakeASR
from hugorm.events import RefinedTurn, SegmentRefined, TranscriptEvent
from hugorm.llm.agent import TurnInput
from hugorm.pipeline.session import SessionConfig, TranscriptionSession


class Collector:
    def __init__(self) -> None:
        self.events: list[TranscriptEvent] = []

    async def __call__(self, event: TranscriptEvent) -> None:
        self.events.append(event)


@dataclass
class StubAgent:
    calls: list[list[TurnInput]] = field(default_factory=list)

    async def refine(self, turns: list[TurnInput], entities, context=None):  # type: ignore[no-untyped-def]
        self.calls.append(list(turns))
        return [
            RefinedTurn(
                speaker=t.speaker,
                start=t.start,
                end=t.end,
                text=f"refined: {t.text}",
            )
            for t in turns
        ]


async def _fetch_empty():
    return []


@pytest.mark.asyncio
async def test_refinement_emits_segment_refined_on_close() -> None:
    asr = FakeASR(words_per_chunk=2)
    emit = Collector()
    agent = StubAgent()
    cfg = SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0)
    session = TranscriptionSession(
        asr=asr,
        diarizer=None,
        emit=emit,
        agent=agent,  # type: ignore[arg-type]
        fetch_entities=_fetch_empty,
        config=cfg,
    )

    await session.start()
    for _ in range(3):
        await session.push_pcm(np.zeros(16000, dtype=np.float32))
    await session.close()

    refined_events = [e for e in emit.events if isinstance(e, SegmentRefined)]
    assert len(refined_events) >= 1
    refined_event = refined_events[-1]
    assert refined_event.end > 0
    assert refined_event.turns
    assert all(t.text.startswith("refined: ") for t in refined_event.turns)
    assert len(agent.calls) >= 1


@pytest.mark.asyncio
async def test_no_refinement_without_agent() -> None:
    asr = FakeASR(words_per_chunk=2)
    emit = Collector()
    cfg = SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0)
    session = TranscriptionSession(asr=asr, diarizer=None, emit=emit, config=cfg)

    await session.start()
    await session.push_pcm(np.zeros(16000, dtype=np.float32))
    await session.close()

    assert not any(isinstance(e, SegmentRefined) for e in emit.events)


@pytest.mark.asyncio
async def test_refined_range_does_not_repeat() -> None:
    asr = FakeASR(words_per_chunk=1)
    emit = Collector()
    agent = StubAgent()
    cfg = SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0)
    session = TranscriptionSession(
        asr=asr,
        diarizer=None,
        emit=emit,
        agent=agent,  # type: ignore[arg-type]
        fetch_entities=_fetch_empty,
        config=cfg,
    )

    await session.start()
    for _ in range(4):
        await session.push_pcm(np.zeros(16000, dtype=np.float32))
    await session.close()

    refined_events = [e for e in emit.events if isinstance(e, SegmentRefined)]
    ranges = [(e.start, e.end) for e in refined_events]
    for i in range(1, len(ranges)):
        assert ranges[i][0] >= ranges[i - 1][1] - 1e-6


def test_group_turns_fills_null_speakers_from_neighbours() -> None:
    from hugorm.events import Word
    from hugorm.pipeline.session import _group_turns

    words = [
        Word(text="a", start=0.0, end=0.2, speaker=None),
        Word(text="b", start=0.2, end=0.4, speaker="S0"),
        Word(text="c", start=0.4, end=0.6, speaker=None),
        Word(text="d", start=0.6, end=0.8, speaker="S0"),
        Word(text="e", start=0.8, end=1.0, speaker=None),
    ]
    turns = _group_turns(words)
    assert len(turns) == 1
    assert turns[0].speaker == "S0"
    assert turns[0].text == "a b c d e"


def test_group_turns_with_all_null_speakers_is_single_unknown_turn() -> None:
    from hugorm.events import Word
    from hugorm.pipeline.session import _group_turns

    words = [
        Word(text="a", start=0.0, end=0.2, speaker=None),
        Word(text="b", start=0.2, end=0.4, speaker=None),
    ]
    turns = _group_turns(words)
    assert len(turns) == 1
    assert turns[0].speaker is None
    assert turns[0].text == "a b"


def test_group_turns_real_speaker_change_still_splits() -> None:
    from hugorm.events import Word
    from hugorm.pipeline.session import _group_turns

    words = [
        Word(text="a", start=0.0, end=0.2, speaker="S0"),
        Word(text="b", start=0.2, end=0.4, speaker="S0"),
        Word(text="c", start=0.4, end=0.6, speaker="S1"),
        Word(text="d", start=0.6, end=0.8, speaker="S1"),
    ]
    turns = _group_turns(words)
    assert [t.speaker for t in turns] == ["S0", "S1"]


@pytest.mark.asyncio
async def test_fetch_entities_called_per_refinement() -> None:
    asr = FakeASR(words_per_chunk=1)
    emit = Collector()
    agent = StubAgent()
    call_count = 0

    async def counting_fetch():
        nonlocal call_count
        call_count += 1
        return []

    cfg = SessionConfig(window_s=1.0, overlap_s=0.0, diarization_interval_s=999.0)
    session = TranscriptionSession(
        asr=asr,
        diarizer=None,
        emit=emit,
        agent=agent,  # type: ignore[arg-type]
        fetch_entities=counting_fetch,
        config=cfg,
    )
    await session.start()
    await session.push_pcm(np.zeros(16000, dtype=np.float32))
    await session.close()

    assert call_count >= 1
