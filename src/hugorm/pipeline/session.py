from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from ..asr.base import ASRBackend
from ..audio.buffer import PCMRingBuffer
from ..audio.chunker import AudioChunk, FixedWindowChunker
from ..diarization.base import DiarizationBackend
from ..events import (
    RefinedTurn,
    SegmentFinalized,
    SegmentRefined,
    SessionEnded,
    SessionStarted,
    SpeakersUpdated,
    TranscriptEvent,
    Word,
    WordsUpserted,
)
from ..graph.store import Entity
from ..llm.agent import RefinementAgent, TurnInput
from .aligner import diar_to_speaker_segments

logger = logging.getLogger(__name__)

Emitter = Callable[[TranscriptEvent], Awaitable[None]]
FetchEntities = Callable[[], Awaitable[list[Entity]]]


@dataclass
class SessionSnapshot:
    session_id: str
    started_at: datetime
    ended_at: datetime
    language: str | None
    words: list[Word] = field(default_factory=list)
    refined_turns: list[RefinedTurn] = field(default_factory=list)


SessionEndHook = Callable[[SessionSnapshot], Awaitable[None]]


@dataclass
class SessionConfig:
    language: str | None = None
    window_s: float = 2.5
    overlap_s: float = 0.25
    diarization_interval_s: float = 5.0
    diarization_window_s: float = 30.0
    finalize_lag_s: float = 10.0
    history_s: float = 90.0
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None


class TranscriptionSession:
    """
    Orchestrates a single streaming transcription session.

    On close, takes a final snapshot of words + refined turns and hands it to
    `on_session_end` (if provided). The caller decides what to do with it —
    typically: persist to postgres, and spawn a post-transcript entity
    extraction as a background task.
    """

    def __init__(
        self,
        asr: ASRBackend,
        diarizer: DiarizationBackend | None,
        emit: Emitter,
        agent: RefinementAgent | None = None,
        fetch_entities: FetchEntities | None = None,
        on_session_end: SessionEndHook | None = None,
        config: SessionConfig | None = None,
    ) -> None:
        self._asr = asr
        self._diar = diarizer
        self._emit = emit
        self._agent = agent
        self._fetch_entities = fetch_entities
        self._on_end = on_session_end
        self._cfg = config or SessionConfig()
        self.session_id = str(uuid.uuid4())
        self._chunker = FixedWindowChunker(
            sample_rate=asr.sample_rate,
            window_s=self._cfg.window_s,
            overlap_s=self._cfg.overlap_s,
        )
        self._buf = PCMRingBuffer(asr.sample_rate, max_seconds=self._cfg.history_s)
        self._seq = 0
        self._asr_tasks: set[asyncio.Task] = set()
        self._refine_tasks: set[asyncio.Task] = set()
        self._diar_task: asyncio.Task | None = None
        self._last_diar_at = 0.0
        self._last_finalized_end = 0.0
        self._last_refined_end = 0.0
        self._closed = False
        self._started = False
        self._detected_language: str | None = None
        self._words: list[Word] = []
        self._refined_turns: list[RefinedTurn] = []
        self._started_at: datetime | None = None

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._started_at = datetime.now(timezone.utc)
        await self._send(SessionStarted(seq=self._next_seq(), session_id=self.session_id))

    async def push_pcm(self, pcm: np.ndarray) -> None:
        if self._closed:
            return
        if not self._started:
            await self.start()
        self._buf.append(pcm)
        for chunk in self._chunker.push(pcm):
            self._spawn_asr(chunk)
        self._maybe_diarize()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for chunk in self._chunker.flush():
            self._spawn_asr(chunk)
        if self._asr_tasks:
            await asyncio.gather(*self._asr_tasks, return_exceptions=True)
        if self._diar_task is not None:
            try:
                await self._diar_task
            except Exception:
                logger.exception("diarization task failed")
        if self._diar is not None and self._buf.duration > 0:
            await self._run_diarization(full=True)
        await self._send(SegmentFinalized(seq=self._next_seq(), end=self._buf.duration))
        if self._refine_tasks:
            await asyncio.gather(*self._refine_tasks, return_exceptions=True)
        if self._on_end is not None:
            try:
                await self._on_end(self._snapshot())
            except Exception:
                logger.exception("on_session_end hook failed")
        await self._send(SessionEnded(seq=self._next_seq()))

    def _snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=self.session_id,
            started_at=self._started_at or datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            language=self._cfg.language or self._detected_language,
            words=[w.model_copy() for w in self._words],
            refined_turns=[t.model_copy() for t in self._refined_turns],
        )

    def _spawn_asr(self, chunk: AudioChunk) -> None:
        task = asyncio.create_task(self._process_chunk(chunk))
        self._asr_tasks.add(task)
        task.add_done_callback(self._asr_tasks.discard)

    async def _process_chunk(self, chunk: AudioChunk) -> None:
        lang = self._cfg.language or self._detected_language
        try:
            result = await self._asr.transcribe(chunk.pcm, chunk.start, language=lang)
        except Exception:
            logger.exception("ASR failed on chunk [%.2f, %.2f]", chunk.start, chunk.end)
            return
        if self._detected_language is None and self._cfg.language is None and result.language:
            self._detected_language = result.language
            logger.info("language locked to '%s'", result.language)
        words = [
            Word(text=w.text, start=w.start, end=w.end, confidence=w.confidence)
            for w in result.words
        ]
        await self._send(
            WordsUpserted(
                seq=self._next_seq(),
                window_start=chunk.start,
                window_end=chunk.end,
                words=words,
            )
        )

    def _maybe_diarize(self) -> None:
        if self._diar is None:
            return
        if self._diar_task is not None and not self._diar_task.done():
            return
        now = self._buf.duration
        if now - self._last_diar_at < self._cfg.diarization_interval_s:
            return
        self._last_diar_at = now
        self._diar_task = asyncio.create_task(self._run_diarization())

    async def _run_diarization(self, full: bool = False) -> None:
        if self._diar is None:
            return
        duration = self._buf.duration
        window_start = 0.0 if full else max(0.0, duration - self._cfg.diarization_window_s)
        window_end = duration
        pcm = self._buf.slice_seconds(window_start, window_end)
        if len(pcm) < self._asr.sample_rate:
            return
        try:
            segs = await self._diar.diarize(
                pcm,
                offset=window_start,
                num_speakers=self._cfg.num_speakers,
                min_speakers=self._cfg.min_speakers,
                max_speakers=self._cfg.max_speakers,
            )
        except Exception:
            logger.exception("diarization failed")
            return
        await self._send(
            SpeakersUpdated(seq=self._next_seq(), segments=diar_to_speaker_segments(segs))
        )
        safe_end = max(0.0, window_end - self._cfg.finalize_lag_s) if not full else window_end
        if safe_end > self._last_finalized_end:
            self._last_finalized_end = safe_end
            await self._send(SegmentFinalized(seq=self._next_seq(), end=safe_end))

    def _apply_words_upserted(self, ev: WordsUpserted) -> None:
        self._words = [
            w for w in self._words
            if not (ev.window_start <= (w.start + w.end) / 2 < ev.window_end)
        ]
        self._words.extend(w.model_copy() for w in ev.words)
        self._words.sort(key=lambda w: w.start)

    def _apply_speakers_updated(self, ev: SpeakersUpdated) -> None:
        for w in self._words:
            mid = (w.start + w.end) / 2
            for s in ev.segments:
                if s.start <= mid < s.end:
                    w.speaker = s.speaker
                    break

    def _apply_segment_refined(self, ev: SegmentRefined) -> None:
        self._refined_turns = [t for t in self._refined_turns if t.end <= ev.start]
        self._refined_turns.extend(t.model_copy() for t in ev.turns)
        self._refined_turns.sort(key=lambda t: t.start)

    def _spawn_refine(self, end: float) -> None:
        if self._agent is None or end <= self._last_refined_end:
            return
        prev_end = self._last_refined_end
        words = [w for w in self._words if prev_end <= w.start < end]
        self._last_refined_end = end
        if not words:
            return
        task = asyncio.create_task(self._refine_range(prev_end, end, words))
        self._refine_tasks.add(task)
        task.add_done_callback(self._refine_tasks.discard)

    async def _refine_range(self, start: float, end: float, words: list[Word]) -> None:
        assert self._agent is not None
        turns = _group_turns(words)
        entities: list[Entity] = []
        if self._fetch_entities is not None:
            try:
                entities = await self._fetch_entities()
            except Exception:
                logger.exception("entity fetch failed — continuing without entities")
        context = list(self._refined_turns)
        try:
            refined = await self._agent.refine(turns, entities, context=context)
        except Exception:
            logger.exception("refinement failed for [%.2f, %.2f]", start, end)
            return
        if not refined:
            return
        await self._send(
            SegmentRefined(seq=self._next_seq(), start=start, end=end, turns=refined)
        )

    async def _send(self, event: TranscriptEvent) -> None:
        if isinstance(event, WordsUpserted):
            self._apply_words_upserted(event)
        elif isinstance(event, SpeakersUpdated):
            self._apply_speakers_updated(event)
        elif isinstance(event, SegmentRefined):
            self._apply_segment_refined(event)
        elif isinstance(event, SegmentFinalized):
            self._spawn_refine(event.end)
        try:
            await self._emit(event)
        except Exception:
            logger.exception("emit failed for event %s", type(event).__name__)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq


def _group_turns(words: list[Word]) -> list[TurnInput]:
    """
    Merge consecutive same-speaker words into one turn. Words with an unknown
    speaker (None — diarization hasn't covered them yet, or missed them) are
    filled in from the nearest neighbour so we don't emit phantom `?` turns
    between labelled spans. This avoids fragmenting the refinement LLM's
    input when diarization coverage is patchy.
    """
    if not words:
        return []

    filled = [w.model_copy() for w in words]
    last_known: str | None = None
    for w in filled:
        if w.speaker is None and last_known is not None:
            w.speaker = last_known
        elif w.speaker is not None:
            last_known = w.speaker
    last_known = None
    for w in reversed(filled):
        if w.speaker is None and last_known is not None:
            w.speaker = last_known
        elif w.speaker is not None:
            last_known = w.speaker

    turns: list[TurnInput] = []
    current: list[Word] = []
    current_speaker: object = _SENTINEL
    for w in filled:
        if w.speaker != current_speaker and current:
            turns.append(_make_turn(len(turns), current_speaker, current))
            current = []
        current_speaker = w.speaker
        current.append(w)
    if current:
        turns.append(_make_turn(len(turns), current_speaker, current))
    return turns


_SENTINEL = object()


def _make_turn(index: int, speaker: object, words: list[Word]) -> TurnInput:
    spk = speaker if isinstance(speaker, str) else None
    text = " ".join(w.text for w in words)
    return TurnInput(
        index=index, speaker=spk, start=words[0].start, end=words[-1].end, text=text
    )
