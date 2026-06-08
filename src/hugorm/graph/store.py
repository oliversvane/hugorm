from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import kuzu


@dataclass
class Entity:
    id: str
    name: str
    type: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""


class GraphStore:
    """
    Single-tenant Kuzu-backed graph. Per-tenant isolation (one DB per tenant)
    is introduced in M3.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self.path))
        self._conn = kuzu.Connection(self._db)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE NODE TABLE IF NOT EXISTS Entity(
                    id STRING PRIMARY KEY,
                    name STRING,
                    type STRING,
                    aliases STRING[],
                    description STRING
                )
                """
            )
            self._conn.execute(
                """
                CREATE REL TABLE IF NOT EXISTS RELATED_TO(
                    FROM Entity TO Entity,
                    rel_type STRING,
                    description STRING
                )
                """
            )

    def upsert_entity(self, e: Entity) -> None:
        params = {
            "id": e.id,
            "name": e.name,
            "type": e.type,
            "aliases": list(e.aliases),
            "description": e.description,
        }
        with self._lock:
            self._conn.execute("MATCH (e:Entity {id: $id}) DETACH DELETE e", {"id": e.id})
            self._conn.execute(
                """
                CREATE (:Entity {
                    id: $id, name: $name, type: $type,
                    aliases: $aliases, description: $description
                })
                """,
                params,
            )

    def all_entities(self) -> list[Entity]:
        with self._lock:
            r = self._conn.execute(
                "MATCH (e:Entity) RETURN e.id, e.name, e.type, e.aliases, e.description"
            )
            out: list[Entity] = []
            while r.has_next():
                row = r.get_next()
                out.append(
                    Entity(
                        id=row[0],
                        name=row[1],
                        type=row[2],
                        aliases=list(row[3] or []),
                        description=row[4] or "",
                    )
                )
            return out

    def relate(self, from_id: str, to_id: str, rel_type: str, description: str = "") -> None:
        with self._lock:
            self._conn.execute(
                """
                MATCH (a:Entity {id: $from_id}), (b:Entity {id: $to_id})
                CREATE (a)-[:RELATED_TO {rel_type: $rel_type, description: $description}]->(b)
                """,
                {"from_id": from_id, "to_id": to_id, "rel_type": rel_type, "description": description},
            )
