"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTenant } from "@/lib/tenant-context";
import { MembersTab } from "./members-tab";
import { PlanTab } from "./plan-tab";
import { TokensTab } from "./tokens-tab";

type TabId = "members" | "plan" | "tokens";

function SettingsInner() {
  const { active } = useTenant();
  const params = useSearchParams();
  const [tab, setTab] = useState<TabId>("members");
  const [banner, setBanner] = useState<string | null>(null);

  useEffect(() => {
    if (params?.get("upgraded") === "1") {
      setTab("plan");
      setBanner("Upgrade successful — refreshing plan…");
    }
  }, [params]);

  if (!active) {
    return <p className="text-gray-500">Select a workspace to manage settings.</p>;
  }

  const tabs: { id: TabId; label: string }[] = [
    { id: "members", label: "Members" },
    { id: "plan", label: "Plan & usage" },
    { id: "tokens", label: "API tokens" },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <p className="text-sm text-gray-500">
        Workspace: <strong>{active.name}</strong> · your role:{" "}
        <strong>{active.role}</strong>
      </p>

      {banner && (
        <div className="bg-green-50 border border-green-200 text-green-800 rounded px-3 py-2 text-sm">
          {banner}
        </div>
      )}

      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-6">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`py-2 text-sm border-b-2 ${
                tab === t.id
                  ? "border-blue-600 text-blue-600 font-medium"
                  : "border-transparent text-gray-600 hover:text-gray-900"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      <div>
        {tab === "members" && <MembersTab />}
        {tab === "plan" && <PlanTab />}
        {tab === "tokens" && <TokensTab />}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<p className="text-gray-500">Loading…</p>}>
      <SettingsInner />
    </Suspense>
  );
}
