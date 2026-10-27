"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { ChevronRight } from "lucide-react";

import { useAppState } from "@/components/providers/app-state";
import { useSession } from "@/components/providers/session-provider";
import { fetcher } from "@/lib/api";
import { useBranding } from "@/lib/branding";
import { MENU, type MenuGroup, type MenuLeaf } from "@/lib/menu";
import { cn } from "@/lib/utils";

import { Logo } from "./logo";

type Summary = { por_grupo?: Record<string, { total: number; critico: number }> };

const SHORTCUTS: Record<string, string> = { "/calendario": "F2" };

function isLeafActive(item: MenuLeaf, pathname: string, search: string) {
  const [path, query] = item.href.split("?");
  if (query) return pathname === path && search.includes(query);
  return pathname === path;
}

/**
 * Menu lateral claro (padrão SIST-SIFAB): grupos em caixa alta, sem ícones; o grupo da tela aberta fica em vermelho.
 * Recolhido, mostra só os ícones dos grupos. Grupo com pendência ganha um ponto laranja.
 */
export function Sidebar() {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const { collapsed, setCollapsed } = useAppState();
  const { me, can, moduleInfo } = useSession();
  const { brasaoUrl } = useBranding(me?.institution?.short_name);
  const { data: summary } = useSWR<Summary>(can("alertas") ? "alerts/summary" : null, fetcher, { refreshInterval: 120_000 });

  const groups = useMemo(() => {
    return MENU.map((g) => {
      if (g.items) {
        const items = g.items.filter((i) => can(i.module));
        return items.length ? { ...g, items } : null;
      }
      return g.module && can(g.module) ? g : null;
    }).filter(Boolean) as MenuGroup[];
  }, [can]);

  const activeGroup = useMemo(
    () => groups.find((g) => g.items
      ? g.items.some((i) => isLeafActive(i, pathname, search) || i.href.split("?")[0] === pathname)
      : g.href === pathname),
    [groups, pathname, search],
  );

  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (activeGroup?.items) setOpen((o) => ({ ...o, [activeGroup.key]: true }));
  }, [activeGroup]);
  const pending = (key: string) => summary?.por_grupo?.[key]?.total ?? 0;

  return (
    <aside className={cn("fixed inset-y-0 left-0 z-30 flex flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200",
      collapsed ? "w-sidebar-collapsed" : "w-sidebar")}>
      <div className={cn("flex h-topbar items-center border-b border-sidebar-border", collapsed ? "justify-center" : "px-3")}>
        <Link href="/" aria-label="Painel Geral" className="min-w-0 flex-1">
          <Logo collapsed={collapsed} crestUrl={brasaoUrl} subtitle={me?.institution?.short_name} />
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-3 thin-scroll" aria-label="Menu principal">
        <ul className="space-y-0.5">
          {groups.map((g) => {
            const Icon = g.icon;
            const isActive = activeGroup?.key === g.key;
            const dot = pending(g.key) > 0 && (
              <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full bg-sidebar-attention", collapsed && "absolute right-2 top-2")}
                title={`${pending(g.key)} pendência(s) na Central de Alertas`} />
            );
            const base = cn("relative flex w-full items-center gap-2 rounded-md text-left transition-colors",
              collapsed ? "h-10 justify-center" : "h-[34px] px-3 text-[11.5px] font-medium uppercase tracking-[0.12em]");
            const color = isActive ? "font-bold text-primary" : "text-sidebar-foreground hover:bg-muted hover:text-foreground";
            if (!g.items) {
              return (
                <li key={g.key}>
                  <Link href={g.href!} title={collapsed ? g.label : undefined} className={cn(base, color)}>
                    {collapsed ? <Icon className="h-[18px] w-[18px]" /> : <span className="flex-1 truncate">{g.label}</span>}
                    {dot}
                  </Link>
                </li>
              );
            }
            const expanded = Boolean(open[g.key]) && !collapsed;
            return (
              <li key={g.key}>
                <button type="button" title={collapsed ? g.label : undefined} aria-expanded={expanded}
                  onClick={() => {
                    if (collapsed) { setCollapsed(false); setOpen((o) => ({ ...o, [g.key]: true })); }
                    else setOpen((o) => ({ ...o, [g.key]: !o[g.key] }));
                  }}
                  className={cn(base, color)}>
                  {collapsed ? <Icon className="h-[18px] w-[18px]" /> : <span className="flex-1 truncate">{g.label}</span>}
                  {dot}
                  {!collapsed && <ChevronRight className={cn("h-3.5 w-3.5 shrink-0 opacity-60 transition-transform", expanded && "rotate-90")} />}
                </button>
                {expanded && (
                  <ul className="mb-2 mt-0.5 space-y-px">
                    {g.items.map((item) => {
                      const active = isLeafActive(item, pathname, search);
                      const info = moduleInfo(item.module);
                      return (
                        <li key={item.href}>
                          <Link href={item.href}
                            className={cn("flex h-8 items-center gap-2 rounded-md border-l-2 pl-5 pr-2.5 text-[13px] transition-colors",
                              active ? "border-primary bg-sidebar-active font-semibold text-sidebar-active-foreground"
                                : info && !info.implemented ? "border-transparent text-sidebar-muted hover:bg-muted"
                                  : "border-transparent text-foreground/80 hover:bg-muted hover:text-foreground")}>
                            <span className="flex-1 truncate">{item.label}</span>
                            {SHORTCUTS[item.href] && <span className="text-[10.5px] text-sidebar-muted">{SHORTCUTS[item.href]}</span>}
                            {info && !info.implemented && !SHORTCUTS[item.href] && <span className="text-[10px] text-sidebar-muted" title="Em desenvolvimento">{info.phase ? `F${info.phase}` : "—"}</span>}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </nav>

      {!collapsed && (
        <div className="mx-3 border-t border-sidebar-border px-1 py-3 text-[11px] leading-[1.45] text-sidebar-muted">
          SIST - FOPAG<br />
          Sistema Integrado de Gestão de RPPS<br />
          {me?.institution?.short_name}<br />
          Operações registradas em auditoria
        </div>
      )}
    </aside>
  );
}
