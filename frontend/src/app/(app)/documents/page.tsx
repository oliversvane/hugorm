"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiUpload } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

type DocRow = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: "uploaded" | "processing" | "processed" | "failed";
  error: string | null;
  created_at: string | null;
};

const TERMINAL = new Set(["processed", "failed"]);

export default function DocumentsPage() {
  const { active } = useTenant();
  const fileRef = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<DocRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (!active) return;
    try {
      const data = await apiGet<DocRow[]>(`/documents?tenant=${active.id}`);
      setRows(data);
      if (data.some((d) => !TERMINAL.has(d.status))) {
        if (pollTimer.current) clearTimeout(pollTimer.current);
        pollTimer.current = setTimeout(load, 2000);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [active]);

  useEffect(() => {
    load();
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [load]);

  const upload = async () => {
    if (!active || !fileRef.current?.files?.[0]) return;
    setBusy(true);
    setErr(null);
    try {
      await apiUpload<DocRow>(`/documents?tenant=${active.id}`, fileRef.current.files[0]);
      fileRef.current.value = "";
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!active) {
    return <p className="text-gray-500">Select a workspace to manage documents.</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Documents</h1>
      <p className="text-sm text-gray-500">
        Upload PDFs or plain-text documents. Domain entities extracted from each
        file join this workspace&apos;s graph and ground future transcriptions.
      </p>

      <div className="flex items-center gap-2 bg-white border border-gray-200 rounded p-3">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
          className="text-sm"
        />
        <button
          type="button"
          onClick={upload}
          disabled={busy}
          className="bg-blue-600 text-white text-sm rounded px-3 py-1 disabled:opacity-60"
        >
          {busy ? "Uploading…" : "Upload"}
        </button>
        <button
          type="button"
          onClick={() => load()}
          className="text-sm text-gray-600 hover:text-gray-900"
        >
          Refresh
        </button>
      </div>

      {err ? <p className="text-sm text-red-600">{err}</p> : null}

      {rows === null ? (
        <p className="text-gray-500">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-gray-500">No documents yet.</p>
      ) : (
        <table className="w-full text-sm bg-white border border-gray-200 rounded">
          <thead className="text-left text-gray-600 bg-gray-50">
            <tr>
              <th className="px-4 py-2">File</th>
              <th className="px-4 py-2">Size</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id} className="border-t border-gray-100">
                <td className="px-4 py-2">{d.filename}</td>
                <td className="px-4 py-2">
                  {(d.size_bytes / 1024).toFixed(1)} KB
                </td>
                <td className={`px-4 py-2 ${statusClass(d.status)}`}>
                  {d.status}
                  {d.error ? `: ${d.error}` : ""}
                </td>
                <td className="px-4 py-2">
                  {d.created_at ? new Date(d.created_at).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function statusClass(status: DocRow["status"]): string {
  switch (status) {
    case "processed":
      return "text-emerald-700";
    case "failed":
      return "text-red-600";
    case "processing":
      return "text-amber-700";
    default:
      return "text-gray-600";
  }
}
