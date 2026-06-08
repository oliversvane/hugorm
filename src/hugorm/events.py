from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class Word(BaseModel):
    text: str
    start: float
    end: float
    speaker: str | None = None
    confidence: float | None = None


class SpeakerSegment(BaseModel):
    start: float
    end: float
    speaker: str


class RefinedTurn(BaseModel):
    speaker: str | None = None
    start: float
    end: float
    text: str
    used_entity_ids: list[str] = Field(default_factory=list)


class SessionStarted(BaseModel):
    type: Literal["session_started"] = "session_started"
    seq: int
    session_id: str


class WordsUpserted(BaseModel):
    """
    Words recognised for a chunk of audio. Clients should replace any previously
    emitted words whose time range falls inside [window_start, window_end] with
    this new set — later chunks can overlap earlier ones and refine them.
    """

    type: Literal["words_upserted"] = "words_upserted"
    seq: int
    window_start: float
    window_end: float
    words: list[Word]


class SpeakersUpdated(BaseModel):
    """
    Retroactive speaker labels for a time range. Clients apply these to words
    whose midpoints fall within a segment.
    """

    type: Literal["speakers_updated"] = "speakers_updated"
    seq: int
    segments: list[SpeakerSegment]


class SegmentFinalized(BaseModel):
    """No further revisions will arrive for audio earlier than `end`."""

    type: Literal["segment_finalized"] = "segment_finalized"
    seq: int
    end: float


class SegmentRefined(BaseModel):
    """
    LLM-refined transcription for a finalized audio range, grouped by speaker
    turn. Emitted alongside per-word events so clients can show both a live
    raw view and a polished refined view.
    """

    type: Literal["segment_refined"] = "segment_refined"
    seq: int
    start: float
    end: float
    turns: list[RefinedTurn]


class SessionEnded(BaseModel):
    type: Literal["session_ended"] = "session_ended"
    seq: int


TranscriptEvent = Annotated[
    Union[
        SessionStarted,
        WordsUpserted,
        SpeakersUpdated,
        SegmentFinalized,
        SegmentRefined,
        SessionEnded,
    ],
    Field(discriminator="type"),
]
