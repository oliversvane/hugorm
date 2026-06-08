from __future__ import annotations

import numpy as np

from hugorm.audio.chunker import FixedWindowChunker


def test_emits_chunks_at_window_size():
    chunker = FixedWindowChunker(sample_rate=16000, window_s=1.0, overlap_s=0.0)
    chunks = chunker.push(np.ones(16000 * 2, dtype=np.float32))
    assert len(chunks) == 2
    assert chunks[0].start == 0.0
    assert abs(chunks[0].end - 1.0) < 1e-6
    assert abs(chunks[1].start - 1.0) < 1e-6


def test_overlap_keeps_tail_samples():
    chunker = FixedWindowChunker(sample_rate=16000, window_s=1.0, overlap_s=0.25)
    samples_per_step = 16000 - 4000
    pcm = np.ones(16000 + samples_per_step, dtype=np.float32)
    chunks = chunker.push(pcm)
    assert len(chunks) == 2
    assert chunks[0].start == 0.0
    assert abs(chunks[0].end - 1.0) < 1e-6
    assert abs(chunks[1].start - 0.75) < 1e-6


def test_flush_emits_remaining():
    chunker = FixedWindowChunker(sample_rate=16000, window_s=1.0, overlap_s=0.0)
    chunker.push(np.ones(8000, dtype=np.float32))
    rem = chunker.flush()
    assert len(rem) == 1
    assert rem[0].pcm.size == 8000


def test_empty_flush_returns_nothing():
    chunker = FixedWindowChunker()
    assert chunker.flush() == []
