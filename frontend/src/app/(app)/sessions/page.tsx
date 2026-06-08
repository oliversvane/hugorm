"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

type SessionRow = {
  id: string;
  started_at: string | null;
  ended_at: string | null;
  language: string | null;
  raw_word_count: number;
  refined_turn_count: number;
};

export default function SessionsPage() {
  const { active } = useTenant();
  const [rows, setRows] = useState<SessionRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    setRows(null);
    setErr(null);
    apiGet<SessionRow[]>(`/sessions?tenant=${active.id}`)
      .then(setRows)
      .catch((e) => setErr(e.message));
  }, [active]);

  if (!active) {
    return <p className="text-gray-500">Select a workspace to view sessions.</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Sessions</h1>
      {err ? <p className="text-red-600 text-sm">{err}</p> : null}
      {rows === null ? (
        <p className="text-gray-500">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-gray-500">
          No sessions yet.{" "}
          <Link href="/live" className="text-blue-600 underline">
            Start a live transcription
          </Link>
          .
        </p>
      ) : (
        <table className="w-full text-sm bg-white border border-gray-200 rounded">
          <thead className="text-left text-gray-600 bg-gray-50">
            <tr>
              <th className="px-4 py-2">Started</th>
              <th className="px-4 py-2">Duration</th>
              <th className="px-4 py-2">Language</th>
              <th className="px-4 py-2">Words</th>
              <th className="px-4 py-2">Refined turns</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-gray-100">
                <td className="px-4 py-2">
                  <Link
                    href={`/sessions/${r.id}`}
                    className="text-blue-600 hover:underline"
                  >
                    {r.started_at
                      ? new Date(r.started_at).toLocaleString()
                      : "—"}
                  </Link>
                </td>
                <td className="px-4 py-2">{formatDuration(r)}</td>
                <td className="px-4 py-2">{r.language ?? "—"}</td>
                <td className="px-4 py-2">{r.raw_word_count}</td>
                <td className="px-4 py-2">{r.refined_turn_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function formatDuration(r: SessionRow): string {
  if (!r.started_at || !r.ended_at) return "—";
  const s = Math.max(
    0,
    (new Date(r.ended_at).getTime() - new Date(r.started_at).getTime()) / 1000,
  );
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}m ${sec}s`;
}
