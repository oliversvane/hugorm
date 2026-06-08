from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model

from ..graph.store import Entity

logger = logging.getLogger(__name__)


class ProposedEntity(BaseModel):
    id: str = Field(
        description=(
            "Stable snake_case slug derived from the canonical name, "
            "e.g. 'openai_gpt_4' for 'OpenAI GPT-4'."
        )
    )
    name: str = Field(description="Canonical name of the entity.")
    type: str = Field(
        description="Short category like 'person', 'product', 'library', 'company', 'concept'."
    )
    aliases: list[str] = Field(
        default_factory=list, description="Alternate spellings or forms seen in the source text."
    )
    description: str = Field(
        default="",
        description="One-sentence summary grounded in the source text. Leave empty if unclear.",
    )
    needs_enrichment: bool = Field(
        default=False,
        description=(
            "Set True if the source text doesn't give you enough to describe this entity. "
            "A later enrichment pass will fill in details."
        ),
    )


class ProposedRelation(BaseModel):
    from_id: str
    to_id: str
    rel_type: str = Field(description="Short edge label, e.g. 'uses', 'works_at', 'released_by'.")
    description: str = ""


class ExtractionOutput(BaseModel):
    entities: list[ProposedEntity] = Field(default_factory=list)
    relations: list[ProposedRelation] = Field(default_factory=list)


DEFAULT_SYSTEM = """
You extract domain entities and relationships from unstructured text for a
knowledge graph that grounds a speech-to-text refinement pipeline.

Rules:
1. Emit entities only for specific named things — people, products, libraries,
   services, projects, locations, companies, or domain concepts. Skip generic
   common nouns.
2. Use a stable snake_case id derived from the canonical name. Reuse an id from
   the "existing entities" list if the text clearly refers to the same thing.
3. Gather alternate spellings or phonetic forms you see in the text as aliases.
4. Write a one-sentence description strictly grounded in the text. If the text
   doesn't say enough, set needs_enrichment=true.
5. Emit relationships only when the text clearly states them.
6. Never invent entities or relationships that aren't supported by the text.
""".strip()


_slug_re = re.compile(r"[^a-z0-9]+")


def _normalize_id(value: str) -> str:
    s = _slug_re.sub("_", value.strip().lower()).strip("_")
    return s or "entity"


class ExtractionAgent:
    """
    pydantic-ai wrapper that turns a chunk of text (plus the tenant's existing
    graph entities as context) into proposed new entities and relationships.
    """

    def __init__(
        self,
        model: Model | KnownModelName | str,
        system_prompt: str | None = None,
    ) -> None:
        self._agent: Agent[None, ExtractionOutput] = Agent(
            model,
            output_type=ExtractionOutput,
            system_prompt=system_prompt or DEFAULT_SYSTEM,
        )

    async def extract(
        self, text: str, existing: list[Entity]
    ) -> ExtractionOutput:
        if not text.strip():
            return ExtractionOutput()
        prompt = self._build_prompt(text, existing)
        try:
            result = await self._agent.run(prompt)
        except Exception:
            logger.exception("extraction agent call failed")
            return ExtractionOutput()
        cleaned = [self._clean(e) for e in result.output.entities]
        return ExtractionOutput(entities=cleaned, relations=result.output.relations)

    @staticmethod
    def _clean(e: ProposedEntity) -> ProposedEntity:
        return ProposedEntity(
            id=_normalize_id(e.id or e.name),
            name=e.name.strip(),
            type=e.type.strip().lower() or "concept",
            aliases=[a.strip() for a in e.aliases if a.strip()],
            description=e.description.strip(),
            needs_enrichment=e.needs_enrichment,
        )

    @staticmethod
    def _build_prompt(text: str, existing: list[Entity]) -> str:
        lines = ["## Existing entities"]
        if existing:
            for e in existing[:100]:
                aliases = f" | aliases: {', '.join(e.aliases)}" if e.aliases else ""
                lines.append(f"- id={e.id} | name={e.name!r} | type={e.type}{aliases}")
        else:
            lines.append("(none)")
        lines.append("")
        lines.append("## Source text")
        lines.append(text.strip())
        return "\n".join(lines)
