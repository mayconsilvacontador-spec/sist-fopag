"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { SWRConfig } from "swr";
import { Loader2 } from "lucide-react";

import { AppStateProvider, useAppState } from "@/components/providers/app-state";
import { SessionProvider, useSession } from "@/components/providers/session-provider";
import { ErrorState } from "@/components/shared/data-states";
import { useBranding } from "@/lib/branding";
import { cn } from "@/lib/utils";

import { PageTabsProvider } from "./page-tabs";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

function Frame({ children }: { children: React.ReactNode }) {
  const { collapsed } = useAppState();
  const { me, loading, error } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  const isPortal = Boolean((me as { portal?: boolean } | undefined)?.portal);
  const { branding, fundoUrl } = useBranding(me?.institution?.short_name);
  // Imagem de fundo da instituição, coberta pelo fundo claro conforme a intensidade escolhida (legibilidade)
  const veil = 1 - (branding?.intensidade ?? 15) / 100;
  const bg = fundoUrl ? {
    backgroundImage: `linear-gradient(hsl(var(--background) / ${veil}), hsl(var(--background) / ${veil})), url("${fundoUrl}")`,
    backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
  } : undefined;
  useEffect(() => {
    if (isPortal) { router.replace("/segurado"); return; }
    if (me?.user.must_change_password && pathname !== "/perfil") router.replace("/perfil?trocar=1");
  }, [me, isPortal, pathname, router]);

  if (loading || isPortal || (!me && !error)) {
    return (
      <div className="flex min-h-screen items-center justify-center text-xs text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Carregando SIST FOPAG...
      </div>
    );
  }
  if (error || !me) {
    return (
      <div className="mx-auto mt-24 max-w-md">
        <ErrorState error={error} />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Na impressão (simulação, CTC) saem o menu, a barra superior e o rodapé */}
      <div className="print:hidden"><Sidebar /></div>
      <div className={cn("flex min-h-screen flex-col transition-[padding] duration-200 print:pl-0", collapsed ? "pl-sidebar-collapsed" : "pl-sidebar")}
        style={bg}>
        <div className="print:hidden"><Topbar /></div>
        <PageTabsProvider userId={me.user.id}>
          <main className="flex-1 px-6 py-5 print:p-0">{children}</main>
        </PageTabsProvider>
        <footer className="px-8 py-3 text-2xs text-muted-foreground print:hidden">
          SIST FOPAG · {me.institution?.name} · Operações registradas em auditoria
        </footer>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ revalidateOnFocus: false, shouldRetryOnError: false }}>
      <SessionProvider>
        <AppStateProvider>
          <Frame>{children}</Frame>
        </AppStateProvider>
      </SessionProvider>
    </SWRConfig>
  );
}
