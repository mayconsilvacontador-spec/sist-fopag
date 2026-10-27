"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Bell, Building2, ChevronLeft, ChevronRight, LogOut, Settings, UserRound } from "lucide-react";

import { useAppState } from "@/components/providers/app-state";
import { useSession } from "@/components/providers/session-provider";
import { SeverityIcon } from "@/components/shared/severity";
import { DemoBadge } from "@/components/shared/status";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { fetcher, type Paginated } from "@/lib/api";
import type { Alert, FiscalYear } from "@/lib/types";
import { cn } from "@/lib/utils";

import { GlobalSearch } from "./global-search";

export function Topbar() {
  const router = useRouter();
  const { exercise, setExercise } = useAppState();
  const { me, can } = useSession();
  // Enquanto a troca de senha obrigatória não é feita, o backend bloqueia as demais rotas
  const blocked = Boolean(me?.user.must_change_password);
  const canAlerts = can("alertas") && !blocked;

  const { data: years } = useSWR<Paginated<FiscalYear>>(blocked ? null : "fiscal-years?page_size=50", fetcher);
  const { data: alerts } = useSWR<Paginated<Alert>>(canAlerts ? "alerts?page_size=6" : null, fetcher, {
    refreshInterval: 120_000,
  });

  const yearOptions = years?.results.map((y) => y.year) ?? [];
  if (!yearOptions.includes(exercise)) yearOptions.push(exercise);
  yearOptions.sort((a, b) => b - a);

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    // Navegação completa para limpar o cache de dados do usuário no navegador
    window.location.assign("/login");
  };

  const switchInstitution = async (id: string) => {
    await fetch("/api/auth/institution", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    window.location.href = "/";
  };

  const initials = (me?.user.full_name || "?")
    .split(" ")
    .filter(Boolean)
    .map((p) => p[0])
    .filter((_, i, arr) => i === 0 || i === arr.length - 1)
    .join("")
    .toUpperCase();

  const iconBtn = "flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground";

  return (
    <header className="sticky top-0 z-20 flex h-topbar items-center gap-4 border-b bg-card px-4">
      <div className="flex shrink-0 items-center gap-1.5">
        <button type="button" onClick={() => router.back()} aria-label="Voltar" title="Voltar"
          className="flex h-9 w-9 items-center justify-center rounded-lg border text-muted-foreground hover:bg-muted hover:text-foreground">
          <ChevronLeft className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => router.forward()} aria-label="Avançar" title="Avançar"
          className="flex h-9 w-9 items-center justify-center rounded-lg border text-muted-foreground hover:bg-muted hover:text-foreground">
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-1 justify-center px-2">
        <GlobalSearch />
      </div>

      <div className="flex items-center gap-1">
        <select id="exercicio" aria-label="Exercício" title="Exercício" value={exercise} onChange={(e) => setExercise(Number(e.target.value))}
          className="mr-2 h-9 cursor-pointer rounded-lg border bg-card px-2.5 text-[14px] font-bold text-foreground focus:outline-none focus:ring-1 focus:ring-ring">
          {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        {canAlerts && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button type="button" className={cn(iconBtn, "relative")} aria-label="Notificações">
                <Bell className="h-[19px] w-[19px]" />
                {(alerts?.count ?? 0) > 0 && (
                  <span className="absolute right-0.5 top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-critical px-1 text-[10px] font-bold text-white ring-2 ring-card">
                    {alerts!.count > 99 ? "99+" : alerts!.count}
                  </span>
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80 p-0">
              <div className="flex items-center justify-between border-b px-3 py-2">
                <span className="text-xs font-semibold">Avisos e pendências</span>
                <span className="text-2xs text-muted-foreground">{alerts?.count ?? 0} abertos</span>
              </div>
              <div className="max-h-80 overflow-y-auto thin-scroll">
                {alerts?.results.map((a) => (
                  <DropdownMenuItem key={a.id} className="items-start rounded-none border-b px-3 py-2 last:border-0" onSelect={() => router.push(a.link || "/alertas")}>
                    <SeverityIcon severity={a.severity} className="mt-0.5" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[12.5px] leading-snug">{a.title}</span>
                      {a.is_demo && <DemoBadge className="mt-1" />}
                    </span>
                  </DropdownMenuItem>
                ))}
                {alerts && alerts.results.length === 0 && (
                  <div className="px-3 py-6 text-center text-xs text-muted-foreground">Nenhuma pendência aberta.</div>
                )}
              </div>
              <Link href="/alertas" className="block border-t px-3 py-2 text-center text-xs font-medium text-primary hover:bg-muted">
                Abrir Central de Alertas
              </Link>
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {can("admin.instituicao") && (
          <Link href="/administracao/instituicao" className={iconBtn} title="Configurações da instituição" aria-label="Configurações">
            <Settings className="h-[19px] w-[19px]" />
          </Link>
        )}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className="ml-2 flex items-center gap-2.5 rounded-lg py-1 pl-2 pr-1.5 hover:bg-muted">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-avatar text-[13px] font-bold text-white">{initials}</span>
              <span className="hidden text-left leading-tight sm:block">
                <span className="block text-[14px] font-semibold text-foreground">{me?.user.short_name ?? "..."}</span>
                <span className="block text-[11.5px] text-muted-foreground">{me?.primary_role ?? ""}</span>
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuLabel>
              <span className="block truncate">{me?.user.full_name}</span>
              <span className="block truncate text-2xs font-normal text-muted-foreground">
                {me?.user.username} · {me?.institution?.short_name}
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => router.push("/perfil")}>
              <UserRound /> Meu perfil e senha
            </DropdownMenuItem>
            {(me?.institutions.length ?? 0) > 1 && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="section-label">Trocar instituição</DropdownMenuLabel>
                {me!.institutions.map((inst) => (
                  <DropdownMenuItem
                    key={inst.id}
                    onSelect={() => switchInstitution(inst.id)}
                    className={cn(inst.id === me?.institution?.id && "font-semibold text-primary")}
                  >
                    <Building2 /> {inst.short_name}
                  </DropdownMenuItem>
                ))}
              </>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={logout}>
              <LogOut /> Sair
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
