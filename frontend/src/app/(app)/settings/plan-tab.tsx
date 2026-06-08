"use client";
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";
import { formatSeconds, UsageBar } from "@/components/usage-bar";

type Usage = {
  plan: "free" | "pro";
  transcription: { used_seconds: number; limit_seconds: number };
  documents: { used: number; limit: number };
};

export function PlanTab() {
  const { active, refresh } = useTenant();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [upgrading, setUpgrading] = useState(false);

  const load = useCallback(async () => {
    if (!active) return;
    try {
      const u = await apiGet<Usage>(`/tenants/${active.id}/usage`);
      setUsage(u);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [active]);

  useEffect(() => {
    load();
    const url = new URL(window.location.href);
    if (url.searchParams.get("upgraded") === "1") {
      const sid = url.searchParams.get("session_id");
      if (sid && active) {
        apiPost<{ plan: string }>(`/tenants/${active.id}/billing/verify`, {
          session_id: sid,
        })
          .then(async () => {
            url.searchParams.delete("upgraded");
            url.searchParams.delete("session_id");
            window.history.replaceState({}, "", url.toString());
            await refresh();
            await load();
          })
          .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
      }
    }
  }, [active, load, refresh]);

  const upgrade = async () => {
    if (!active) return;
    setErr(null);
    setUpgrading(true);
    try {
      const { url } = await apiPost<{ url: string }>(
        `/tenants/${active.id}/billing/checkout`,
        {},
      );
      window.location.href = url;
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setErr("Stripe is not configured on this server.");
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
      setUpgrading(false);
    }
  };

  if (!usage) return <p className="text-gray-500">Loading…</p>;

  const isPro = usage.plan === "pro";

  return (
    <div className="space-y-6">
      {err ? <p className="text-sm text-red-600">{err}</p> : null}

      <section className="bg-white border border-gray-200 rounded p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-gray-500">Current plan</div>
            <div className="text-xl font-semibold capitalize">{usage.plan}</div>
          </div>
          {active?.role === "owner" && !isPro && (
            <button
              type="button"
              onClick={upgrade}
              disabled={upgrading}
              className="bg-blue-600 text-white text-sm rounded px-4 py-2 disabled:opacity-60"
            >
              {upgrading ? "Redirecting to checkout…" : "Upgrade to Pro"}
            </button>
          )}
        </div>
      </section>

      <section className="bg-white border border-gray-200 rounded p-4 space-y-4">
        <h2 className="text-sm font-medium">This month</h2>
        <UsageBar
          label="Transcription time"
          used={usage.transcription.used_seconds}
          limit={usage.transcription.limit_seconds}
          formatter={formatSeconds}
        />
        <UsageBar
          label="Documents uploaded"
          used={usage.documents.used}
          limit={usage.documents.limit}
        />
      </section>
    </div>
  );
}
