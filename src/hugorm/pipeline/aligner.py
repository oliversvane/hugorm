from __future__ import annotations

from ..asr.base import ASRWord
from ..diarization.base import DiarSegment
from ..events import SpeakerSegment, Word


def assign_speakers(words: list[ASRWord], diar: list[DiarSegment]) -> list[Word]:
    """Label each word using the diarization segment containing its midpoint."""
    out: list[Word] = []
    for w in words:
        mid = (w.start + w.end) / 2
        speaker: str | None = None
        for d in diar:
            if d.start <= mid < d.end:
                speaker = d.speaker
                break
        out.append(
            Word(
                text=w.text,
                start=w.start,
                end=w.end,
                speaker=speaker,
                confidence=w.confidence,
            )
        )
    return out


def diar_to_speaker_segments(diar: list[DiarSegment]) -> list[SpeakerSegment]:
    return [SpeakerSegment(start=d.start, end=d.end, speaker=d.speaker) for d in diar]
