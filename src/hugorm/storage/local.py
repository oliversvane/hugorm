from __future__ import annotations

import asyncio
from pathlib import Path

from .base import StorageError


class LocalObjectStorage:
    """
    Filesystem-backed storage for development and as a fallback when the
    Supabase Storage service is unavailable. Files are written under
    `root/<path>`; subdirectories are created on demand.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _full(self, path: str) -> Path:
        path = path.lstrip("/")
        if ".." in Path(path).parts:
            raise StorageError(f"invalid path: {path}")
        return self._root / path

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        target = self._full(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, data)

    async def get(self, path: str) -> bytes:
        target = self._full(path)
        if not target.is_file():
            raise StorageError(f"not found: {path}")
        return await asyncio.to_thread(target.read_bytes)

    async def delete(self, path: str) -> None:
        target = self._full(path)
        if target.is_file():
            await asyncio.to_thread(target.unlink)

    async def ensure_ready(self) -> None:
        return None
