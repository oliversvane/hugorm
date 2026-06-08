from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import av
import numpy as np
from aiortc import MediaStreamTrack, RTCDataChannel, RTCPeerConnection

from ..asr.base import ASRBackend
from ..diarization.base import DiarizationBackend
from ..events import TranscriptEvent
from ..graph.store import Entity
from ..llm.agent import RefinementAgent
from ..pipeline.session import (
    SessionConfig,
    SessionEndHook,
    TranscriptionSession,
)

logger = logging.getLogger(__name__)


FetchEntities = Callable[[], Awaitable[list[Entity]]]


class WebRTCAudioSink:
    """
    Binds an inbound WebRTC audio track to a TranscriptionSession and writes
    events back over the client-created data channel.

    The session's refinement graph is provided as a `fetch_entities` callable,
    which the caller usually composes from a per-tenant and a per-user
    GraphStore in multi-tenant mode. `on_session_end` is invoked with the
    final snapshot before the session is closed.
    """

    TARGET_SR = 16000

    def __init__(
        self,
        pc: RTCPeerConnection,
        asr: ASRBackend,
        diarizer: DiarizationBackend | None,
        agent: RefinementAgent | None = None,
        fetch_entities: FetchEntities | None = None,
        on_session_end: SessionEndHook | None = None,
        session_config: SessionConfig | None = None,
    ) -> None:
        self._pc = pc
        self._asr = asr
        self._diar = diarizer
        self._agent = agent
        self._fetch_entities = fetch_entities
        self._on_end = on_session_end
        self._session_config = session_config
        self._session: TranscriptionSession | None = None
        self._channel: RTCDataChannel | None = None
        self._consume_task: asyncio.Task | None = None
        self._resampler = av.AudioResampler(format="flt", layout="mono", rate=self.TARGET_SR)

        @pc.on("datachannel")
        def _on_datachannel(channel: RTCDataChannel) -> None:
            self._channel = channel

        @pc.on("track")
        def _on_track(track: MediaStreamTrack) -> None:
            if track.kind != "audio":
                return
            self._consume_task = asyncio.create_task(self._consume(track))

        @pc.on("connectionstatechange")
        async def _on_state() -> None:
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await self.close()

    async def _emit(self, event: TranscriptEvent) -> None:
        channel = self._channel
        if channel is None or channel.readyState != "open":
            return
        channel.send(event.model_dump_json())

    async def _consume(self, track: MediaStreamTrack) -> None:
        session = TranscriptionSession(
            asr=self._asr,
            diarizer=self._diar,
            emit=self._emit,
            agent=self._agent,
            fetch_entities=self._fetch_entities,
            on_session_end=self._on_end,
            config=self._session_config,
        )
        self._session = session
        await session.start()
        try:
            while True:
                frame = await track.recv()
                for resampled in self._resampler.resample(frame):
                    arr = resampled.to_ndarray()
                    pcm = arr.reshape(-1).astype(np.float32)
                    await session.push_pcm(pcm)
        except Exception as e:  # noqa: BLE001
            logger.info("audio track terminated: %s", e)
        finally:
            await session.close()

    async def close(self) -> None:
        task = self._consume_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self._session is not None and not self._session._closed:  # noqa: SLF001
            await self._session.close()
