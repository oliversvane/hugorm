import type { ReactNode } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Nav } from "@/components/nav";
import { TenantProvider } from "@/lib/tenant-context";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <TenantProvider>
        <Nav />
        <main className="max-w-6xl mx-auto px-6 py-6">{children}</main>
      </TenantProvider>
    </AuthGuard>
  );
}
