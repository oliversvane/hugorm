from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from hugorm.extraction.agent import ExtractionAgent, _normalize_id
from hugorm.graph.store import Entity


def test_normalize_id_slugifies() -> None:
    assert _normalize_id("OpenAI GPT-4") == "openai_gpt_4"
    assert _normalize_id("  hello  world!!  ") == "hello_world"
    assert _normalize_id("") == "entity"


@pytest.mark.asyncio
async def test_extract_with_empty_text_returns_empty() -> None:
    agent = ExtractionAgent(model=TestModel())
    out = await agent.extract("", [])
    assert out.entities == []
    assert out.relations == []


@pytest.mark.asyncio
async def test_extract_returns_structured_output() -> None:
    agent = ExtractionAgent(model=TestModel())
    out = await agent.extract("The team uses pyannote for diarization.", [Entity(id="pyannote", name="pyannote", type="library")])
    # TestModel returns schema-valid output; we just verify it's the right shape.
    for e in out.entities:
        assert e.id == e.id.lower().replace(" ", "_") or e.id == "entity"
        assert e.type == e.type.lower()


def test_build_prompt_lists_existing_and_text() -> None:
    existing = [Entity(id="pyannote", name="pyannote", type="library", aliases=["pyanote"])]
    prompt = ExtractionAgent._build_prompt("sample text about pyannote", existing)
    assert "id=pyannote" in prompt
    assert "sample text about pyannote" in prompt
    assert "aliases: pyanote" in prompt
