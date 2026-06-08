"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

type Word = {
  text: string;
  start: number;
  end: number;
  speaker: string | null;
};
type RefinedTurn = {
  start: number;
  end: number;
  speaker: string | null;
  text: string;
  used_entity_ids: string[];
};
type SessionDetail = {
  id: string;
  started_at: string | null;
  ended_at: string | null;
  language: string | null;
  raw_words: Word[];
  refined_turns: RefinedTurn[];
};

const PALETTE = ["bg-blue-50", "bg-amber-50", "bg-emerald-50", "bg-rose-50", "bg-violet-50"];

function speakerClass(speakerMap: Map<string, number>, spk: string | null): string {
  if (!spk) return "";
  if (!speakerMap.has(spk)) speakerMap.set(spk, speakerMap.size);
  return PALETTE[speakerMap.get(spk)! % PALETTE.length];
}

export default function SessionDetailPage() {
  const params = useParams<{ id: string }>();
  const { active } = useTenant();
  const [data, setData] = useState<SessionDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!active || !params?.id) return;
    apiGet<SessionDetail>(`/sessions/${params.id}?tenant=${active.id}`)
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [active, params?.id]);

  if (err) return <p className="text-red-600 text-sm">{err}</p>;
  if (!data) return <p className="text-gray-500">Loading…</p>;

  const speakerMap = new Map<string, number>();

  return (
    <div className="space-y-6">
      <div>
        <Link href="/sessions" className="text-sm text-blue-600 hover:underline">
          ← Sessions
        </Link>
        <h1 className="text-2xl font-semibold mt-1">
          {data.started_at ? new Date(data.started_at).toLocaleString() : "Session"}
        </h1>
        <p className="text-sm text-gray-500">
          {data.language ?? "—"} · {data.raw_words.length} words ·{" "}
          {data.refined_turns.length} refined turns
        </p>
      </div>

      <section className="grid md:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded p-4">
          <h2 className="text-sm font-medium text-gray-700 mb-2">Raw</h2>
          <div className="text-sm leading-relaxed whitespace-pre-wrap">
            {data.raw_words.map((w, i) => (
              <span
                key={i}
                className={`inline-block px-0.5 rounded ${speakerClass(
                  speakerMap,
                  w.speaker,
                )}`}
                title={`${w.start.toFixed(2)}–${w.end.toFixed(2)}s${
                  w.speaker ? ` · ${w.speaker}` : ""
                }`}
              >
                {w.text}{" "}
              </span>
            ))}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded p-4">
          <h2 className="text-sm font-medium text-gray-700 mb-2">Refined</h2>
          <div className="space-y-2">
            {data.refined_turns.map((t, i) => (
              <div
                key={i}
                className={`rounded px-2 py-1 text-sm ${speakerClass(
                  speakerMap,
                  t.speaker,
                )}`}
              >
                <span className="text-xs font-medium text-gray-600 mr-2">
                  {t.speaker ?? "?"}:
                </span>
                {t.text}
                {t.used_entity_ids.length > 0 && (
                  <span className="ml-2 text-xs text-gray-500">
                    [{t.used_entity_ids.join(", ")}]
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
