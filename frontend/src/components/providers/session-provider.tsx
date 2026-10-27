"use client";

import { createContext, useCallback, useContext, useMemo } from "react";
import useSWR from "swr";

import { fetcher } from "@/lib/api";
import type { Me, ModuleInfo } from "@/lib/types";

type SessionValue = {
  me: Me | undefined;
  loading: boolean;
  error: unknown;
  can: (module: string, action?: string) => boolean;
  moduleInfo: (code: string) => ModuleInfo | undefined;
  reload: () => void;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { data, error, isLoading, mutate } = useSWR<Me>("auth/me", fetcher, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  const perms = useMemo(() => new Set(data?.permissions ?? []), [data]);
  const modules = useMemo(() => new Map((data?.modules ?? []).map((m) => [m.code, m])), [data]);

  const can = useCallback(
    (module: string, action = "visualizar") => perms.has(`${module}:${action}`),
    [perms],
  );
  const moduleInfo = useCallback((code: string) => modules.get(code), [modules]);

  const value = useMemo<SessionValue>(
    () => ({ me: data, loading: isLoading, error, can, moduleInfo, reload: () => void mutate() }),
    [data, isLoading, error, can, moduleInfo, mutate],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession deve ser usado dentro de SessionProvider");
  return ctx;
}
