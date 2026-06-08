"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiBaseUrl, apiPost, ApiError } from "@/lib/api";
import { getSupabase } from "@/lib/supabase";

type Preview = {
  email: string;
  role: string;
  tenant_name: string;
  expires_at: string;
};

function AcceptInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params?.get("token") ?? "";

  const [authed, setAuthed] = useState<boolean | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const supabase = getSupabase();
    supabase.auth.getSession().then(({ data: { session } }) => {
      setAuthed(!!session);
    });
  }, []);

  useEffect(() => {
    if (!token) return;
    fetch(`${apiBaseUrl()}/invitations/${encodeURIComponent(token)}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      })
      .then(setPreview)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [token]);

  const accept = useCallback(async () => {
    if (!token) return;
    setErr(null);
    setBusy(true);
    try {
      const { tenant_id } = await apiPost<{ tenant_id: string }>(
        `/invitations/${encodeURIComponent(token)}/accept`,
      );
      window.localStorage.setItem("hugorm:tenant", tenant_id);
      router.replace("/live");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setErr("This invitation was issued to a different email. Sign in with that address.");
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
      setBusy(false);
    }
  }, [token, router]);

  if (!token) return <div className="p-6">Missing invitation token.</div>;
  if (err) return <div className="p-6 text-red-600">{err}</div>;
  if (!preview) return <div className="p-6 text-gray-500">Loading invitation…</div>;

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <h1 className="text-xl font-semibold">You&apos;ve been invited</h1>
        <p className="text-sm text-gray-700">
          Join <strong>{preview.tenant_name}</strong> as{" "}
          <strong>{preview.role}</strong>.
        </p>
        <p className="text-xs text-gray-500">Issued to {preview.email}.</p>

        {authed === false && (
          <div className="space-y-2">
            <p className="text-sm text-gray-700">
              You need to sign in with <strong>{preview.email}</strong> to accept.
            </p>
            <button
              type="button"
              onClick={() => {
                window.localStorage.setItem("hugorm:invite", token);
                router.push("/login");
              }}
              className="w-full bg-blue-600 text-white text-sm rounded py-2"
            >
              Sign in to continue
            </button>
          </div>
        )}

        {authed && (
          <button
            type="button"
            onClick={accept}
            disabled={busy}
            className="w-full bg-blue-600 text-white text-sm rounded py-2 disabled:opacity-60"
          >
            {busy ? "Accepting…" : "Accept invitation"}
          </button>
        )}
      </div>
    </div>
  );
}

export default function AcceptPage() {
  return (
    <Suspense fallback={<div className="p-6 text-gray-500">Loading…</div>}>
      <AcceptInner />
    </Suspense>
  );
}
