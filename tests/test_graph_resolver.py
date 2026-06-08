from __future__ import annotations

from pathlib import Path

import pytest

from hugorm.graph.resolver import GraphResolver
from hugorm.graph.store import Entity


@pytest.mark.asyncio
async def test_tenants_are_isolated(tmp_path: Path) -> None:
    resolver = GraphResolver(tmp_path)
    a = await resolver.tenant_store("tenant-a")
    b = await resolver.tenant_store("tenant-b")
    a.upsert_entity(Entity(id="x", name="Alpha", type="t"))
    b.upsert_entity(Entity(id="x", name="Bravo", type="t"))
    a_ents = a.all_entities()
    b_ents = b.all_entities()
    assert [e.name for e in a_ents] == ["Alpha"]
    assert [e.name for e in b_ents] == ["Bravo"]


@pytest.mark.asyncio
async def test_user_and_tenant_graphs_are_separate(tmp_path: Path) -> None:
    resolver = GraphResolver(tmp_path)
    tenant = await resolver.tenant_store("t1")
    user = await resolver.user_store("t1", "u1")
    tenant.upsert_entity(Entity(id="t-only", name="Tenant Thing", type="t"))
    user.upsert_entity(Entity(id="u-only", name="User Thing", type="t"))

    entities = await resolver.fetch_entities("t1", "u1")
    ids = {e.id for e in entities}
    assert ids == {"t-only", "u-only"}


@pytest.mark.asyncio
async def test_same_key_returns_cached_store(tmp_path: Path) -> None:
    resolver = GraphResolver(tmp_path)
    a1 = await resolver.tenant_store("tenant-a")
    a2 = await resolver.tenant_store("tenant-a")
    assert a1 is a2


@pytest.mark.asyncio
async def test_lru_evicts_oldest(tmp_path: Path) -> None:
    resolver = GraphResolver(tmp_path, max_stores=2)
    a = await resolver.tenant_store("a")
    await resolver.tenant_store("b")
    await resolver.tenant_store("c")  # should evict "a"
    a_again = await resolver.tenant_store("a")
    assert a_again is not a
