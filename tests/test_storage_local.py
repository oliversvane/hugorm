from __future__ import annotations

from pathlib import Path

import pytest

from hugorm.storage.base import StorageError
from hugorm.storage.local import LocalObjectStorage


@pytest.mark.asyncio
async def test_put_and_get_roundtrip(tmp_path: Path) -> None:
    s = LocalObjectStorage(tmp_path)
    await s.put("tenant/abc/hello.txt", b"hello", "text/plain")
    out = await s.get("tenant/abc/hello.txt")
    assert out == b"hello"


@pytest.mark.asyncio
async def test_get_missing_raises(tmp_path: Path) -> None:
    s = LocalObjectStorage(tmp_path)
    with pytest.raises(StorageError):
        await s.get("nope.txt")


@pytest.mark.asyncio
async def test_path_traversal_rejected(tmp_path: Path) -> None:
    s = LocalObjectStorage(tmp_path)
    with pytest.raises(StorageError):
        await s.put("../outside.txt", b"x", "text/plain")


@pytest.mark.asyncio
async def test_delete_is_idempotent(tmp_path: Path) -> None:
    s = LocalObjectStorage(tmp_path)
    await s.delete("does-not-exist.txt")
    await s.put("x.txt", b"a", "text/plain")
    await s.delete("x.txt")
    with pytest.raises(StorageError):
        await s.get("x.txt")
