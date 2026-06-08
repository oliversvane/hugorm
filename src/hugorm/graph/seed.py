from __future__ import annotations

from .store import Entity


def demo_entities() -> list[Entity]:
    """
    A tiny synthetic seed so M2 has something to ground the refinement LLM on.
    Real domain data arrives via document ingestion in M4.
    """
    return [
        Entity(
            id="hugorm",
            name="Hugorm",
            type="project",
            aliases=["Hugo", "Hugo Worm", "Huge Arm"],
            description="Streaming diarized speech-to-text platform.",
        ),
        Entity(
            id="pyannote",
            name="pyannote.audio",
            type="library",
            aliases=["pyannote", "pyanote", "pie annote"],
            description="Python toolkit for speaker diarization.",
        ),
        Entity(
            id="faster_whisper",
            name="faster-whisper",
            type="library",
            aliases=["Faster Whisper", "Fast Whisper", "Whisper"],
            description="CTranslate2 Whisper inference engine.",
        ),
        Entity(
            id="kuzu",
            name="Kùzu",
            type="database",
            aliases=["Kuzu", "Coozoo", "Ku zoo"],
            description="Embedded property graph database.",
        ),
        Entity(
            id="pydantic_ai",
            name="Pydantic AI",
            type="library",
            aliases=["pydantic-ai", "Pi Dantic AI", "Pydantic Agent"],
            description="Agent framework producing validated pydantic outputs.",
        ),
        Entity(
            id="supabase",
            name="Supabase",
            type="service",
            aliases=["Soupabase", "Soup Abase"],
            description="Open-source Postgres-backed auth and realtime stack.",
        ),
        Entity(
            id="webrtc",
            name="WebRTC",
            type="protocol",
            aliases=["Web R T C", "Web RTC"],
            description="Real-time browser audio and video protocol.",
        ),
        Entity(
            id="aiortc",
            name="aiortc",
            type="library",
            aliases=["AIO RTC", "Aya Our T C"],
            description="Python WebRTC implementation built on asyncio.",
        ),
    ]
