"use client";
import { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import { useTenant } from "@/lib/tenant-context";

type Member = {
  user_id: string;
  email: string | null;
  role: "owner" | "admin" | "member";
  created_at: string;
};

type Invitation = {
  id: string;
  email: string;
  role: string;
  token: string;
  invite_url: string;
  expires_at: string;
  created_at: string;
};

const CAN_INVITE = new Set(["owner", "admin"]);

export function MembersTab() {
  const { active } = useTenant();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [invites, setInvites] = useState<Invitation[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "admin">("member");
  const [busy, setBusy] = useState(false);
  const [justCreated, setJustCreated] = useState<Invitation | null>(null);

  const canInvite = active && CAN_INVITE.has(active.role);

  const load = useCallback(async () => {
    if (!active) return;
    try {
      const [m, i] = await Promise.all([
        apiGet<Member[]>(`/tenants/${active.id}/members`),
        canInvite
          ? apiGet<Invitation[]>(`/tenants/${active.id}/invitations`)
          : Promise.resolve([] as Invitation[]),
      ]);
      setMembers(m);
      setInvites(i);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [active, canInvite]);

  useEffect(() => {
    load();
  }, [load]);

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!active) return;
    setErr(null);
    setBusy(true);
    try {
      const inv = await apiPost<Invitation>(
        `/tenants/${active.id}/invitations`,
        { email, role },
      );
      setJustCreated(inv);
      setEmail("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (userId: string) => {
    if (!active) return;
    if (!confirm("Remove this member from the workspace?")) return;
    try {
      await apiDelete(`/tenants/${active.id}/members/${userId}`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const cancelInvite = async (id: string) => {
    if (!active) return;
    try {
      await apiDelete(`/tenants/${active.id}/invitations/${id}`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-6">
      {err ? <p className="text-sm text-red-600">{err}</p> : null}

      {canInvite && (
        <section className="bg-white border border-gray-200 rounded p-4 space-y-3">
          <h2 className="text-sm font-medium">Invite someone</h2>
          <form onSubmit={invite} className="flex flex-wrap gap-2">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@example.com"
              className="flex-1 min-w-40 border border-gray-300 rounded px-2 py-1 text-sm"
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as "member" | "admin")}
              className="border border-gray-300 rounded px-2 py-1 text-sm"
            >
              <option value="member">member</option>
              <option value="admin">admin</option>
            </select>
            <button
              type="submit"
              disabled={busy}
              className="bg-blue-600 text-white text-sm rounded px-3 py-1 disabled:opacity-60"
            >
              {busy ? "…" : "Create invite"}
            </button>
          </form>
          {justCreated && (
            <div className="bg-green-50 border border-green-200 rounded p-3 text-sm space-y-1">
              <div>
                Invite created for <strong>{justCreated.email}</strong>. Share this
                URL:
              </div>
              <code className="block break-all bg-white border border-green-200 rounded px-2 py-1 text-xs">
                {justCreated.invite_url}
              </code>
            </div>
          )}
        </section>
      )}

      <section className="bg-white border border-gray-200 rounded">
        <h2 className="px-4 py-2 text-sm font-medium border-b border-gray-200">
          Members ({members?.length ?? "…"})
        </h2>
        <ul className="divide-y divide-gray-100">
          {(members ?? []).map((m) => (
            <li
              key={m.user_id}
              className="px-4 py-2 flex items-center justify-between text-sm"
            >
              <div>
                <div>{m.email ?? m.user_id.slice(0, 8)}</div>
                <div className="text-xs text-gray-500">
                  {m.role} · since {new Date(m.created_at).toLocaleDateString()}
                </div>
              </div>
              {canInvite && m.role !== "owner" && (
                <button
                  type="button"
                  onClick={() => remove(m.user_id)}
                  className="text-xs text-red-600 hover:underline"
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      {canInvite && invites && invites.length > 0 && (
        <section className="bg-white border border-gray-200 rounded">
          <h2 className="px-4 py-2 text-sm font-medium border-b border-gray-200">
            Pending invitations
          </h2>
          <ul className="divide-y divide-gray-100">
            {invites.map((i) => (
              <li
                key={i.id}
                className="px-4 py-2 flex items-center justify-between text-sm"
              >
                <div>
                  <div>{i.email}</div>
                  <div className="text-xs text-gray-500">
                    {i.role} · expires{" "}
                    {new Date(i.expires_at).toLocaleDateString()}
                  </div>
                  <code className="block text-xs text-gray-500 break-all mt-1">
                    {i.invite_url}
                  </code>
                </div>
                <button
                  type="button"
                  onClick={() => cancelInvite(i.id)}
                  className="text-xs text-red-600 hover:underline"
                >
                  Cancel
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
