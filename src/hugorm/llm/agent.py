from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model

from ..events import RefinedTurn
from ..graph.store import Entity

logger = logging.getLogger(__name__)


# Guardrail: if the LLM returns fewer than this fraction of the input's words,
# treat it as a catastrophic over-edit and fall back to the raw text so we
# don't lose content. The new prompt forbids removals, so this should be rare.
_MIN_WORD_RATIO = 0.5


@dataclass
class TurnInput:
    """A speaker turn extracted from raw ASR output, handed to the refinement LLM."""

    index: int
    speaker: str | None
    start: float
    end: float
    text: str


class AgentRefinedTurn(BaseModel):
    index: int = Field(description="Index of the input turn this corresponds to, starting at 0.")
    text: str = Field(description="Refined transcription text in the source language.")
    used_entity_ids: list[str] = Field(
        default_factory=list,
        description="IDs of entities from the Candidate list whose canonical name you substituted into the text.",
    )


class AgentOutput(BaseModel):
    turns: list[AgentRefinedTurn] = Field(
        description="One entry per input turn, in the same order, with the same index values."
    )


DEFAULT_SYSTEM = """
You polish raw streaming ASR transcripts that may contain recognition errors.
This is a LIGHT copy-edit, not a rewrite.

Hard rules — violating these ruins the transcript:

1. PRESERVE EVERY SPOKEN WORD. Do not remove, summarise, or paraphrase content
   to make the text shorter or more fluent. Keep filler words, repetitions,
   partial words, and awkward phrasing intact. If the input is
   "um, what if we... yeah, okay, what if we wait", the output must contain
   all of that, not a cleaner version of it.

2. Only change words that are clearly ASR mistakes:
   - Garbled proper nouns that phonetically match a candidate entity → replace
     ONLY that span with the entity's canonical name.
   - Obvious single-word mis-hearings (e.g. "their" vs "there") → fix only the
     one word.
   If you are not sure a word is wrong, leave it alone.

3. Never invent entities or details that aren't in the Candidate entities list
   or the source turns.

4. Preserve speaker attribution and turn order. Return exactly one output turn
   per INPUT turn, using the same index. Context turns are shown so you see
   what was already said — do NOT emit output for them.

5. Do not translate. Keep the source language exactly (Danish stays Danish,
   English stays English).

6. Output only the corrected transcription text — no commentary, timestamps,
   or markdown.

7. In `used_entity_ids`, list the ids of entities whose canonical names you
   substituted into the turn. Empty list if no substitutions.

Example (entity substitution; every other word preserved):

  INPUT:    "and then we sent it through faster whisker for processing"
  CANDIDATE: id=faster_whisper | name='faster-whisper' | aliases: Faster Whisper
  OUTPUT text: "and then we sent it through faster-whisper for processing"
  used_entity_ids: ["faster_whisper"]
""".strip()


class RefinementAgent:
    """Wraps a pydantic-ai Agent with a structured refinement contract."""

    def __init__(
        self,
        model: Model | KnownModelName | str,
        system_prompt: str | None = None,
        context_turns: int = 3,
    ) -> None:
        self._agent: Agent[None, AgentOutput] = Agent(
            model,
            output_type=AgentOutput,
            system_prompt=system_prompt or DEFAULT_SYSTEM,
        )
        self._context_turns = max(0, context_turns)

    async def refine(
        self,
        turns: list[TurnInput],
        entities: list[Entity],
        context: list[RefinedTurn] | None = None,
    ) -> list[RefinedTurn]:
        if not turns:
            return []
        context = (context or [])[-self._context_turns :]
        prompt = self._build_prompt(turns, entities, context)
        try:
            result = await self._agent.run(prompt)
        except Exception:
            logger.exception("refinement agent call failed — returning raw turns")
            return [_fallback_turn(t) for t in turns]

        refined_by_idx = {t.index: t for t in result.output.turns}
        out: list[RefinedTurn] = []
        for src in turns:
            r = refined_by_idx.get(src.index)
            if r is None or not r.text.strip():
                out.append(_fallback_turn(src))
                continue
            if _too_short(r.text, src.text):
                logger.warning(
                    "refined turn %d dropped content (%d → %d words) — falling back to raw",
                    src.index,
                    len(src.text.split()),
                    len(r.text.split()),
                )
                out.append(_fallback_turn(src))
                continue
            out.append(
                RefinedTurn(
                    speaker=src.speaker,
                    start=src.start,
                    end=src.end,
                    text=r.text.strip(),
                    used_entity_ids=list(r.used_entity_ids),
                )
            )
        return out

    @staticmethod
    def _build_prompt(
        turns: list[TurnInput],
        entities: list[Entity],
        context: list[RefinedTurn],
    ) -> str:
        lines: list[str] = []
        if context:
            lines.append("## Context (already refined — DO NOT emit output for these)")
            for t in context:
                speaker = t.speaker or "SPEAKER_?"
                lines.append(f"({speaker}) {t.text}")
            lines.append("")
        lines.append("## Raw diarized turns (refine these)")
        for t in turns:
            speaker = t.speaker or "SPEAKER_?"
            lines.append(f"[{t.index}] ({speaker}, {t.start:.2f}-{t.end:.2f}s) {t.text}")
        lines.append("")
        lines.append("## Candidate entities")
        if entities:
            for e in entities:
                aliases = f" | aliases: {', '.join(e.aliases)}" if e.aliases else ""
                desc = f" | {e.description}" if e.description else ""
                lines.append(f"- id={e.id} | name={e.name!r} | type={e.type}{aliases}{desc}")
        else:
            lines.append("(none)")
        lines.append("")
        lines.append("Return one output turn per input turn, matching input indexes.")
        return "\n".join(lines)


def _too_short(refined: str, original: str) -> bool:
    orig_words = original.split()
    if len(orig_words) < 3:
        return False
    return len(refined.split()) < _MIN_WORD_RATIO * len(orig_words)


def _fallback_turn(src: TurnInput) -> RefinedTurn:
    return RefinedTurn(
        speaker=src.speaker, start=src.start, end=src.end, text=src.text, used_entity_ids=[]
    )
