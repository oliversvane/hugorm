"use client";
import { useState } from "react";
import { apiPost, ApiError } from "@/lib/api";
import { useTenant, type Tenant } from "@/lib/tenant-context";

export function TenantSwitcher() {
  const { tenants, active, setActive, refresh } = useTenant();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setErr(null);
    if (!name.trim()) return;
    const slug = name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "");
    if (!slug) {
      setErr("name needs at least one alphanumeric character");
      return;
    }
    setBusy(true);
    try {
      const t = await apiPost<Tenant>("/tenants", { name: name.trim(), slug });
      await refresh();
      setActive(t.id);
      setName("");
      setOpen(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setErr("slug already taken");
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-sm border border-gray-300 rounded px-2 py-1 bg-white hover:bg-gray-50"
      >
        {active ? active.name : "Select workspace"}
        <span className="ml-1 text-gray-400">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-72 bg-white border border-gray-200 rounded shadow-lg z-20 p-2 space-y-1">
          {tenants.length === 0 && (
            <div className="text-sm text-gray-500 px-2 py-1">
              You have no workspaces yet. Create one below.
            </div>
          )}
          {tenants.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => {
                setActive(t.id);
                setOpen(false);
              }}
              className={`w-full text-left px-2 py-1 rounded text-sm ${
                active?.id === t.id ? "bg-blue-50" : "hover:bg-gray-50"
              }`}
            >
              <div>{t.name}</div>
              <div className="text-xs text-gray-500">{t.role}</div>
            </button>
          ))}
          <div className="border-t border-gray-200 pt-2 mt-2 space-y-1">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="New workspace name"
              className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
            />
            {err ? <div className="text-xs text-red-600">{err}</div> : null}
            <button
              type="button"
              disabled={busy}
              onClick={create}
              className="w-full text-sm bg-blue-600 text-white rounded px-2 py-1 disabled:opacity-60"
            >
              {busy ? "…" : "Create workspace"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
