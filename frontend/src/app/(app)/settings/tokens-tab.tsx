"use client";
import { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

type TokenRow = {
  id: string;
  name: string;
  prefix: string;
  last_used_at: string | null;
  created_at: string;
};

type CreatedToken = TokenRow & { token: string };

export function TokensTab() {
  const { active } = useTenant();
  const [tokens, setTokens] = useState<TokenRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [justCreated, setJustCreated] = useState<CreatedToken | null>(null);

  const load = useCallback(async () => {
    if (!active) return;
    try {
      const rows = await apiGet<TokenRow[]>(`/tenants/${active.id}/api_tokens`);
      setTokens(rows);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [active]);

  useEffect(() => {
    load();
  }, [load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!active || !name.trim()) return;
    setErr(null);
    setBusy(true);
    try {
      const row = await apiPost<CreatedToken>(
        `/tenants/${active.id}/api_tokens`,
        { name: name.trim() },
      );
      setJustCreated(row);
      setName("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    if (!active) return;
    if (!confirm("Revoke this API token? Any scripts using it will stop working."))
      return;
    try {
      await apiDelete(`/tenants/${active.id}/api_tokens/${id}`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-6">
      {err ? <p className="text-sm text-red-600">{err}</p> : null}

      <section className="bg-white border border-gray-200 rounded p-4 space-y-3">
        <h2 className="text-sm font-medium">Create an API token</h2>
        <p className="text-xs text-gray-500">
          Use tokens to call the Hugorm API from scripts. Scoped to this workspace.
        </p>
        <form onSubmit={create} className="flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. cron-ingest"
            className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm"
            required
          />
          <button
            type="submit"
            disabled={busy}
            className="bg-blue-600 text-white text-sm rounded px-3 py-1 disabled:opacity-60"
          >
            {busy ? "…" : "Create"}
          </button>
        </form>
        {justCreated && (
          <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm space-y-1">
            <div className="font-medium">
              Copy this token now — it won&apos;t be shown again.
            </div>
            <code className="block break-all bg-white border border-amber-200 rounded px-2 py-1 text-xs">
              {justCreated.token}
            </code>
            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(justCreated.token);
              }}
              className="text-xs text-blue-600 underline"
            >
              Copy
            </button>
            <button
              type="button"
              onClick={() => setJustCreated(null)}
              className="text-xs text-gray-600 underline ml-3"
            >
              Dismiss
            </button>
          </div>
        )}
      </section>

      <section className="bg-white border border-gray-200 rounded">
        <h2 className="px-4 py-2 text-sm font-medium border-b border-gray-200">
          Active tokens ({tokens?.length ?? "…"})
        </h2>
        {tokens && tokens.length === 0 ? (
          <div className="px-4 py-3 text-sm text-gray-500">No tokens yet.</div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {(tokens ?? []).map((t) => (
              <li
                key={t.id}
                className="px-4 py-2 flex items-center justify-between text-sm"
              >
                <div>
                  <div>{t.name}</div>
                  <div className="text-xs text-gray-500">
                    <code>hgrm_{t.prefix}…</code> · created{" "}
                    {new Date(t.created_at).toLocaleDateString()}
                    {t.last_used_at &&
                      ` · last used ${new Date(t.last_used_at).toLocaleDateString()}`}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => revoke(t.id)}
                  className="text-xs text-red-600 hover:underline"
                >
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
