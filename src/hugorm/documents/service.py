from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from ..db.postgres import Database, DocumentRow
from ..extraction.agent import ExtractionAgent
from ..graph.resolver import GraphResolver
from ..graph.store import Entity
from ..storage.base import ObjectStorage
from .parser import UnsupportedDocumentError, parse_document

logger = logging.getLogger(__name__)


_unsafe_path_chars = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_storage_name(filename: str) -> str:
    """
    Supabase Storage only accepts a limited character set in object keys
    (letters, digits, `.`, `_`, `-`, `/`). Map anything else to `_` so files
    like `"Jensløvsvej 15, 3. th.pdf"` don't get rejected.
    """
    base = PurePosixPath(filename).name or "file"
    cleaned = _unsafe_path_chars.sub("_", base).strip("._") or "file"
    return cleaned[:120]


@dataclass
class DocumentRecord:
    id: UUID
    tenant_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    error: str | None = None


SpawnTask = Callable[[Awaitable[None]], None]


class DocumentService:
    """
    Upload, persist, and process documents. Processing runs in the background
    via `spawn_task`; caller's request returns as soon as the file is stored
    and the metadata row is written (status = 'uploaded').
    """

    TEXT_CHAR_LIMIT = 30_000

    def __init__(
        self,
        db: Database,
        storage: ObjectStorage,
        resolver: GraphResolver,
        agent: ExtractionAgent | None,
        spawn_task: SpawnTask,
    ) -> None:
        self._db = db
        self._storage = storage
        self._resolver = resolver
        self._agent = agent
        self._spawn = spawn_task

    async def upload(
        self,
        tenant_id: UUID,
        user_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> DocumentRecord:
        doc_id = uuid.uuid4()
        storage_path = f"{tenant_id}/{doc_id}/{_safe_storage_name(filename)}"
        await self._storage.put(storage_path, data, content_type)
        await self._db.insert_document(
            DocumentRow(
                id=doc_id,
                tenant_id=tenant_id,
                user_id=UUID(user_id),
                filename=filename,
                content_type=content_type,
                size_bytes=len(data),
                storage_path=storage_path,
                status="uploaded",
            )
        )
        self._spawn(self._process(doc_id, tenant_id))
        return DocumentRecord(
            id=doc_id,
            tenant_id=tenant_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            status="uploaded",
        )

    async def list_for_tenant(self, tenant_id: UUID) -> list[DocumentRow]:
        return await self._db.list_documents(tenant_id)

    async def _process(self, doc_id: UUID, tenant_id: UUID) -> None:
        try:
            await self._db.set_document_status(doc_id, "processing")
            row = await self._db.get_document(doc_id)
            if row is None:
                return
            blob = await self._storage.get(row.storage_path)
            text = await parse_document(blob, row.content_type, row.filename)
            if not text.strip():
                await self._db.set_document_status(doc_id, "processed", error="empty text")
                return
            if self._agent is None:
                await self._db.set_document_status(doc_id, "processed", error="LLM disabled")
                return
            tenant_store = await self._resolver.tenant_store(str(tenant_id))
            existing = await self._read_existing(tenant_store)
            result = await self._agent.extract(text[: self.TEXT_CHAR_LIMIT], existing)
            for proposed in result.entities:
                tenant_store.upsert_entity(
                    Entity(
                        id=proposed.id,
                        name=proposed.name,
                        type=proposed.type,
                        aliases=list(proposed.aliases),
                        description=proposed.description,
                    )
                )
                await self._db.record_entity_source(
                    tenant_id=tenant_id,
                    entity_id=proposed.id,
                    source_type="document",
                    source_ref=doc_id,
                    needs_enrichment=proposed.needs_enrichment,
                )
            for rel in result.relations:
                try:
                    tenant_store.relate(rel.from_id, rel.to_id, rel.rel_type, rel.description)
                except Exception:
                    logger.debug("skipped rel %s -[%s]-> %s", rel.from_id, rel.rel_type, rel.to_id)
            await self._db.set_document_status(doc_id, "processed")
            logger.info(
                "document %s processed: %d entities, %d relations",
                doc_id, len(result.entities), len(result.relations),
            )
        except UnsupportedDocumentError as e:
            await self._db.set_document_status(doc_id, "failed", error=str(e))
        except Exception as e:
            logger.exception("document processing failed for %s", doc_id)
            await self._db.set_document_status(doc_id, "failed", error=str(e))

    @staticmethod
    async def _read_existing(store) -> list[Entity]:
        import asyncio

        return await asyncio.to_thread(store.all_entities)
