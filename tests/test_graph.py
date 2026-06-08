from __future__ import annotations

from pathlib import Path

import pytest

from hugorm.graph.seed import demo_entities
from hugorm.graph.store import Entity, GraphStore


@pytest.fixture()
def store(tmp_path: Path) -> GraphStore:
    return GraphStore(tmp_path / "test.kuzu")


def test_roundtrip_single_entity(store: GraphStore) -> None:
    e = Entity(id="x1", name="Xavier", type="person", aliases=["X", "Xav"], description="test")
    store.upsert_entity(e)
    got = store.all_entities()
    assert len(got) == 1
    assert got[0].id == "x1"
    assert got[0].name == "Xavier"
    assert got[0].aliases == ["X", "Xav"]
    assert got[0].description == "test"


def test_upsert_is_idempotent(store: GraphStore) -> None:
    store.upsert_entity(Entity(id="x1", name="One", type="thing"))
    store.upsert_entity(Entity(id="x1", name="Two", type="thing"))
    got = store.all_entities()
    assert len(got) == 1
    assert got[0].name == "Two"


def test_seed_loads_all_demo_entities(store: GraphStore) -> None:
    entities = demo_entities()
    for e in entities:
        store.upsert_entity(e)
    got = {e.id: e for e in store.all_entities()}
    assert set(got) == {e.id for e in entities}
