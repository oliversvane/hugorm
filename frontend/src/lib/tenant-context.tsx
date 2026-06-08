"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { apiGet } from "./api";

export type Tenant = {
  id: string;
  name: string;
  slug: string;
  role: string;
};

type Ctx = {
  tenants: Tenant[];
  active: Tenant | null;
  setActive: (id: string) => void;
  refresh: () => Promise<void>;
};

const TenantContext = createContext<Ctx>({
  tenants: [],
  active: null,
  setActive: () => {},
  refresh: async () => {},
});

export function TenantProvider({ children }: { children: ReactNode }) {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const data = await apiGet<Tenant[]>("/me/tenants");
    setTenants(data);
    const saved =
      typeof window !== "undefined"
        ? window.localStorage.getItem("hugorm:tenant")
        : null;
    const preferred = data.find((t) => t.id === saved) ?? data[0];
    setActiveId(preferred?.id ?? null);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  const setActive = useCallback((id: string) => {
    setActiveId(id);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("hugorm:tenant", id);
    }
  }, []);

  const active = tenants.find((t) => t.id === activeId) ?? null;

  return (
    <TenantContext.Provider value={{ tenants, active, setActive, refresh }}>
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant() {
  return useContext(TenantContext);
}
