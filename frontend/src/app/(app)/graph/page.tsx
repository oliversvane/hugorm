"use client";
import { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

type Entity = {
  id: string;
  name: string;
  type: string;
  aliases: string[];
  description: string;
};

export default function GraphPage() {
  const { active } = useTenant();
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!active) return;
    setEntities(null);
    setErr(null);
    apiGet<Entity[]>(`/graph/entities?tenant=${active.id}`)
      .then(setEntities)
      .catch((e) => setErr(e.message));
  }, [active]);

  const filtered = useMemo(() => {
    if (!entities) return entities;
    const q = filter.trim().toLowerCase();
    if (!q) return entities;
    return entities.filter(
      (e) =>
        e.id.toLowerCase().includes(q) ||
        e.name.toLowerCase().includes(q) ||
        e.type.toLowerCase().includes(q) ||
        e.aliases.some((a) => a.toLowerCase().includes(q)),
    );
  }, [entities, filter]);

  const byType = useMemo(() => {
    if (!filtered) return new Map<string, Entity[]>();
    const m = new Map<string, Entity[]>();
    for (const e of filtered) {
      const list = m.get(e.type) ?? [];
      list.push(e);
      m.set(e.type, list);
    }
    return new Map([...m.entries()].sort(([a], [b]) => a.localeCompare(b)));
  }, [filtered]);

  if (!active) {
    return <p className="text-gray-500">Select a workspace to explore its graph.</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Graph</h1>
      <p className="text-sm text-gray-500">
        Entities in this workspace. Populated by document ingestion and
        post-transcript extraction. Used to ground live transcription.
      </p>

      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter by name, type, or alias…"
        className="w-full md:w-80 border border-gray-300 rounded px-3 py-1.5 text-sm"
      />

      {err ? <p className="text-sm text-red-600">{err}</p> : null}

      {entities === null ? (
        <p className="text-gray-500">Loading…</p>
      ) : entities.length === 0 ? (
        <p className="text-gray-500">
          No entities yet. Upload a document or complete a live session.
        </p>
      ) : filtered && filtered.length === 0 ? (
        <p className="text-gray-500">No matches.</p>
      ) : (
        <div className="space-y-6">
          {[...byType.entries()].map(([type, list]) => (
            <section key={type}>
              <h2 className="text-sm font-medium text-gray-700 mb-2 uppercase tracking-wide">
                {type}{" "}
                <span className="text-xs text-gray-400">({list.length})</span>
              </h2>
              <ul className="bg-white border border-gray-200 rounded divide-y divide-gray-100">
                {list.map((e) => (
                  <li key={e.id} className="px-4 py-2 text-sm">
                    <div className="font-medium">{e.name}</div>
                    <div className="text-xs text-gray-500">
                      <code>{e.id}</code>
                      {e.aliases.length > 0 ? (
                        <> · aliases: {e.aliases.join(", ")}</>
                      ) : null}
                    </div>
                    {e.description ? (
                      <div className="text-gray-700 mt-0.5">{e.description}</div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
