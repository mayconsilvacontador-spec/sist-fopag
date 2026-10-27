"use client";

/**
 * Abas de navegação (como no navegador): cada tela aberta vira uma aba; clicar troca de tela, o "x" (ou o botão
 * do meio do mouse) fecha. As abas e a posição de rolagem de cada uma ficam guardadas neste navegador.
 *
 * Observação: ao trocar de aba a tela é remontada (o Next.js não mantém telas ocultas vivas); os dados voltam
 * do cache na hora, mas texto digitado e não salvo em um formulário se perde.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, Home, PanelLeft, X, XSquare } from "lucide-react";

import { useAppState } from "@/components/providers/app-state";

import { findScreenByPath } from "@/lib/menu";
import { cn } from "@/lib/utils";

type Tab = { href: string; title: string };
type Ctx = { setTitle: (title: string) => void };

const TabsContext = createContext<Ctx>({ setTitle: () => undefined });
const MAX_TABS = 15;

function storageKey(userId: string) {
  return `sist.tabs.${userId}`;
}

function load(userId: string): Tab[] {
  try {
    const raw = localStorage.getItem(storageKey(userId));
    const tabs = raw ? (JSON.parse(raw) as Tab[]) : [];
    return Array.isArray(tabs) ? tabs.filter((t) => typeof t.href === "string" && t.href.startsWith("/")) : [];
  } catch {
    return [];
  }
}

function save(userId: string, tabs: Tab[]) {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(tabs));
  } catch {
    /* armazenamento indisponível: as abas valem só nesta sessão */
  }
}

function fallbackTitle(pathname: string): string {
  const screen = findScreenByPath(pathname);
  if (screen) return screen.label;
  if (pathname === "/") return "Painel Geral";
  const last = pathname.split("/").filter(Boolean).pop() ?? "";
  return /^[0-9a-f-]{20,}$/i.test(last) ? "Carregando…" : last.replace(/-/g, " ");
}

/** Usado pelo PageHeader para dar à aba atual o título da tela (ex.: nome da pessoa). */
export function useTabTitle(title: string) {
  const { setTitle } = useContext(TabsContext);
  useEffect(() => {
    if (title) setTitle(title);
  }, [title, setTitle]);
}

/** Componente invisível colocado no PageHeader. */
export function TabTitle({ title }: { title: string }) {
  useTabTitle(title);
  return null;
}

export function PageTabsProvider({ userId, children }: { userId: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const search = useSearchParams();
  const router = useRouter();
  const strip = useRef<HTMLDivElement>(null);
  const { collapsed, setCollapsed } = useAppState();
  const href = pathname + (search.toString() ? `?${search.toString()}` : "");
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [ready, setReady] = useState(false);
  const scrolls = useRef<Record<string, number>>({});
  const titles = useRef<Record<string, string>>({}); // título informado pela tela (pode chegar antes da aba existir)
  const current = useRef(href);
  const tabKey = (h: string) => h.split("?")[0]; // a aba é a tela; filtros na URL não criam aba nova

  useEffect(() => {
    setTabs(load(userId));
    setReady(true);
  }, [userId]);

  // Abre (ou ativa) a aba da tela atual e restaura a rolagem dela
  useEffect(() => {
    if (!ready) return;
    const prev = current.current;
    scrolls.current[tabKey(prev)] = window.scrollY;
    current.current = href;
    setTabs((ts) => {
      const i = ts.findIndex((t) => tabKey(t.href) === tabKey(href));
      let next: Tab[];
      if (i >= 0) {
        next = ts.map((t, j) => (j === i ? { ...t, href } : t));
      } else {
        next = [...ts, { href, title: titles.current[tabKey(href)] ?? fallbackTitle(pathname) }];
        if (next.length > MAX_TABS) next = next.slice(next.length - MAX_TABS); // descarta a aba mais antiga
      }
      save(userId, next);
      return next;
    });
    const y = scrolls.current[tabKey(href)];
    if (y) requestAnimationFrame(() => window.scrollTo(0, y));
  }, [href, pathname, ready, userId]);

  const activeKey = tabKey(href);
  const setTitle = useCallback((title: string) => {
    titles.current[activeKey] = title;
    setTabs((ts) => {
      const key = activeKey;
      if (!ts.some((t) => tabKey(t.href) === key && t.title !== title)) return ts;
      const next = ts.map((t) => (tabKey(t.href) === key ? { ...t, title } : t));
      save(userId, next);
      return next;
    });
  }, [userId, activeKey]);

  const close = (h: string) => {
    const i = tabs.findIndex((t) => t.href === h);
    const next = tabs.filter((t) => t.href !== h);
    setTabs(next);
    save(userId, next);
    if (tabKey(h) === tabKey(href)) {
      const target = next[i] ?? next[i - 1];
      router.push(target ? target.href : "/");
    }
  };

  const closeOthers = () => {
    const keep = tabs.filter((t) => tabKey(t.href) === tabKey(href));
    setTabs(keep);
    save(userId, keep);
  };

  return (
    <TabsContext.Provider value={{ setTitle }}>
      <div className="sticky top-[var(--topbar-height)] z-10 flex items-center gap-2 border-b bg-card px-3 pt-1.5 print:hidden">
        <button type="button" onClick={() => setCollapsed(!collapsed)} title={collapsed ? "Expandir menu" : "Recolher menu"}
          aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
          className="mb-1.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground">
          <PanelLeft className="h-4 w-4" />
        </button>
        <div ref={strip} className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none]" role="tablist" aria-label="Telas abertas">
          {tabs.map((t) => {
            const active = tabKey(t.href) === tabKey(href);
            const home = tabKey(t.href) === "/";
            return (
              <div key={tabKey(t.href)} role="tab" aria-selected={active}
                className={cn("group -mb-px flex max-w-[230px] shrink-0 items-center border-b-2 text-[13px]",
                  active ? "border-primary font-medium text-primary" : "border-transparent text-muted-foreground hover:text-foreground")}
                onAuxClick={(e) => { if (e.button === 1) { e.preventDefault(); close(t.href); } }}
                title={t.title}>
                <button type="button" className="flex items-center gap-1.5 truncate py-1.5 pl-3 pr-1 text-left" onClick={() => { if (!active) router.push(t.href); }}>
                  {home && <Home className="h-3.5 w-3.5 shrink-0" />}
                  <span className="truncate">{t.title}</span>
                </button>
                <button type="button" aria-label={`Fechar ${t.title}`} onClick={() => close(t.href)}
                  className={cn("mr-1 rounded p-0.5 hover:bg-muted", active ? "opacity-60" : "opacity-0 group-hover:opacity-60 focus:opacity-60")}>
                  <X className="h-3 w-3" />
                </button>
              </div>
            );
          })}
        </div>
        <button type="button" onClick={() => strip.current?.scrollBy({ left: 300, behavior: "smooth" })} title="Mais abas"
          className="shrink-0 rounded p-1 text-muted-foreground hover:bg-card hover:text-foreground">
          <ChevronRight className="h-4 w-4" />
        </button>
        {tabs.length > 1 && (
          <button type="button" onClick={closeOthers} title="Fechar as outras abas"
            className="shrink-0 rounded p-1 text-muted-foreground hover:bg-card hover:text-foreground">
            <XSquare className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {children}
    </TabsContext.Provider>
  );
}
