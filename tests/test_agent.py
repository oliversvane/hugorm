from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from hugorm.graph.store import Entity
from hugorm.llm.agent import RefinementAgent, TurnInput


@pytest.mark.asyncio
async def test_empty_turns_returns_empty() -> None:
    agent = RefinementAgent(model=TestModel())
    result = await agent.refine([], [])
    assert result == []


@pytest.mark.asyncio
async def test_refine_preserves_turn_count_and_timestamps() -> None:
    agent = RefinementAgent(model=TestModel())
    turns = [
        TurnInput(index=0, speaker="SPEAKER_00", start=0.0, end=1.0, text="hello"),
        TurnInput(index=1, speaker="SPEAKER_01", start=1.2, end=2.4, text="world"),
    ]
    entities = [Entity(id="e1", name="World", type="word")]
    result = await agent.refine(turns, entities)
    assert len(result) == 2
    assert result[0].start == 0.0 and result[0].end == 1.0
    assert result[0].speaker == "SPEAKER_00"
    assert result[1].start == 1.2 and result[1].end == 2.4
    assert result[1].speaker == "SPEAKER_01"


def test_prompt_includes_turns_and_entities() -> None:
    turns = [TurnInput(index=0, speaker="A", start=0.0, end=1.0, text="hey hugo")]
    entities = [Entity(id="hugorm", name="Hugorm", type="project", aliases=["Hugo"])]
    prompt = RefinementAgent._build_prompt(turns, entities, [])
    assert "hey hugo" in prompt
    assert "id=hugorm" in prompt
    assert "aliases: Hugo" in prompt


def test_prompt_handles_empty_entities() -> None:
    turns = [TurnInput(index=0, speaker="A", start=0.0, end=1.0, text="x")]
    prompt = RefinementAgent._build_prompt(turns, [], [])
    assert "(none)" in prompt


def test_prompt_includes_context_when_provided() -> None:
    from hugorm.events import RefinedTurn

    turns = [TurnInput(index=0, speaker="A", start=2.0, end=3.0, text="second")]
    context = [RefinedTurn(speaker="A", start=0.0, end=1.0, text="earlier refined text")]
    prompt = RefinementAgent._build_prompt(turns, [], context)
    assert "already refined" in prompt
    assert "earlier refined text" in prompt
    assert "second" in prompt


def test_too_short_triggers_at_half_words() -> None:
    from hugorm.llm.agent import _too_short

    original = "one two three four five six seven eight"
    assert _too_short("two three four", original) is True
    assert _too_short("one two three four five six", original) is False


def test_too_short_leaves_short_turns_alone() -> None:
    from hugorm.llm.agent import _too_short

    assert _too_short("", "yes") is False
    assert _too_short("no", "yes") is False
