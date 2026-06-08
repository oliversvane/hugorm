"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getSupabase } from "@/lib/supabase";
import { TenantSwitcher } from "./tenant-switcher";

const LINKS = [
  { href: "/live", label: "Live" },
  { href: "/sessions", label: "Sessions" },
  { href: "/documents", label: "Documents" },
  { href: "/graph", label: "Graph" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  const signOut = async () => {
    await getSupabase().auth.signOut();
    router.replace("/login");
  };

  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="max-w-6xl mx-auto flex items-center gap-6 px-6 py-3">
        <Link href="/" className="font-semibold">
          Hugorm
        </Link>
        <div className="flex items-center gap-4">
          {LINKS.map((l) => {
            const active = pathname === l.href || pathname?.startsWith(l.href + "/");
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`text-sm ${
                  active ? "text-blue-600 font-medium" : "text-gray-700 hover:text-gray-900"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-3">
          <TenantSwitcher />
          <button
            type="button"
            onClick={signOut}
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
