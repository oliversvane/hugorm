from __future__ import annotations

from hugorm.asr.base import ASRWord
from hugorm.diarization.base import DiarSegment
from hugorm.pipeline.aligner import assign_speakers, diar_to_speaker_segments


def test_assigns_speaker_by_word_midpoint():
    words = [
        ASRWord(text="hello", start=0.0, end=0.5),
        ASRWord(text="world", start=0.6, end=1.0),
        ASRWord(text="goodbye", start=1.2, end=1.8),
    ]
    diar = [
        DiarSegment(start=0.0, end=1.1, speaker="SPEAKER_00"),
        DiarSegment(start=1.1, end=2.0, speaker="SPEAKER_01"),
    ]
    out = assign_speakers(words, diar)
    assert [w.speaker for w in out] == ["SPEAKER_00", "SPEAKER_00", "SPEAKER_01"]


def test_word_outside_any_segment_has_none_speaker():
    words = [ASRWord(text="stray", start=5.0, end=5.5)]
    diar = [DiarSegment(start=0.0, end=1.0, speaker="S0")]
    out = assign_speakers(words, diar)
    assert out[0].speaker is None


def test_diar_to_speaker_segments_preserves_fields():
    diar = [DiarSegment(start=0.5, end=1.5, speaker="SPK")]
    segs = diar_to_speaker_segments(diar)
    assert len(segs) == 1
    assert (segs[0].start, segs[0].end, segs[0].speaker) == (0.5, 1.5, "SPK")
