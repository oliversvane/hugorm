"""
Seed the demo graph for a specific tenant.

Usage:
    uv run python scripts/seed_graph.py --tenant <tenant_uuid>
    uv run python scripts/seed_graph.py --tenant <tenant_uuid> --user <user_uuid>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hugorm.config import Settings  # noqa: E402
from hugorm.graph.resolver import GraphResolver  # noqa: E402
from hugorm.graph.seed import demo_entities  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True, help="tenant UUID")
    ap.add_argument("--user", default=None, help="user UUID (seeds user graph instead of tenant)")
    args = ap.parse_args()

    settings = Settings()
    resolver = GraphResolver(settings.data_dir)
    if args.user:
        path = resolver.user_path(args.tenant, args.user)
    else:
        path = resolver.tenant_path(args.tenant)

    from hugorm.graph.store import GraphStore

    store = GraphStore(path)
    entities = demo_entities()
    for e in entities:
        store.upsert_entity(e)
    print(f"seeded {len(entities)} entities into {path}")
    for e in store.all_entities():
        print(f"  - {e.id}: {e.name} ({e.type})")


if __name__ == "__main__":
    main()
