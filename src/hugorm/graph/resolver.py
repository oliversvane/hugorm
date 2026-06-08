from __future__ import annotations

import asyncio
from collections import OrderedDict
from pathlib import Path

from .store import Entity, GraphStore


class GraphResolver:
    """
    LRU-pooled provider of per-tenant and per-user Kuzu graph stores.

    Layout on disk:
        <root>/tenants/<tenant_id>/tenant.kuzu
        <root>/tenants/<tenant_id>/users/<user_id>.kuzu

    Evicted stores are dropped from the cache; Python GC finalizes the Kuzu
    handles. The pool is sized so an idle tenant doesn't hold a connection
    forever, but active tenants stay hot.
    """

    def __init__(self, root: str | Path, max_stores: int = 64) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._max = max_stores
        self._stores: OrderedDict[tuple[str, ...], GraphStore] = OrderedDict()
        self._lock = asyncio.Lock()

    def tenant_path(self, tenant_id: str) -> Path:
        return self._root / "tenants" / tenant_id / "tenant.kuzu"

    def user_path(self, tenant_id: str, user_id: str) -> Path:
        return self._root / "tenants" / tenant_id / "users" / f"{user_id}.kuzu"

    async def tenant_store(self, tenant_id: str) -> GraphStore:
        return await self._get(("t", tenant_id), self.tenant_path(tenant_id))

    async def user_store(self, tenant_id: str, user_id: str) -> GraphStore:
        return await self._get(("u", tenant_id, user_id), self.user_path(tenant_id, user_id))

    async def fetch_entities(self, tenant_id: str, user_id: str) -> list[Entity]:
        tenant = await self.tenant_store(tenant_id)
        user = await self.user_store(tenant_id, user_id)
        tenant_ents, user_ents = await asyncio.gather(
            asyncio.to_thread(tenant.all_entities),
            asyncio.to_thread(user.all_entities),
        )
        return tenant_ents + user_ents

    async def _get(self, key: tuple[str, ...], path: Path) -> GraphStore:
        async with self._lock:
            if key in self._stores:
                self._stores.move_to_end(key)
                return self._stores[key]
            store = await asyncio.to_thread(GraphStore, path)
            self._stores[key] = store
            while len(self._stores) > self._max:
                self._stores.popitem(last=False)
            return store
