from __future__ import annotations

from typing import Protocol


class StorageError(Exception):
    pass


class ObjectStorage(Protocol):
    """
    Abstract blob store. Both LocalObjectStorage and SupabaseObjectStorage
    conform to this so document upload/processing doesn't care which is in use.
    """

    async def put(self, path: str, data: bytes, content_type: str) -> None: ...

    async def get(self, path: str) -> bytes: ...

    async def delete(self, path: str) -> None: ...

    async def ensure_ready(self) -> None: ...
