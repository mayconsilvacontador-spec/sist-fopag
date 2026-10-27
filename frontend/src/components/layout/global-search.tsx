"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, LayoutGrid, Loader2, Search } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { api } from "@/lib/api";
import { flatScreens } from "@/lib/menu";
import { cn } from "@/lib/utils";

type Item = { id: string; title: string; subtitle?: string; href: string };
type Group = { key: string; label: string; items: Item[] };

function normalize(s: string) {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/**
 * Pesquisa global: telas (local, conforme permissões) + registros do backend.
 * Atalho: Ctrl+K. Resultados aparecem sem sair da página.
 */
export function GlobalSearch() {
  const router = useRouter();
  const { can } = useSession();
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  const [remote, setRemote] = useState<Group[]>([]);
  const [loading, setLoading] = useState(false);
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  const screens = useMemo(() => flatScreens().filter((s) => can(s.module)), [can]);

  const localGroup: Group | null = useMemo(() => {
    const t = normalize(term.trim());
    if (t.length < 2) return null;
    const items = screens
      .filter((s) => normalize(`${s.label} ${s.group}`).includes(t))
      .slice(0, 6)
      .map((s) => ({ id: s.href, title: s.label, subtitle: s.group, href: s.href }));
    return items.length ? { key: "telas", label: "Telas", items } : null;
  }, [term, screens]);

  useEffect(() => {
    const t = term.trim();
    if (t.length < 2) {
      setRemote([]);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api<{ groups: Group[] }>(`search?q=${encodeURIComponent(t)}`, { signal: ctrl.signal });
        setRemote(data.groups);
      } catch {
        /* pesquisa é auxiliar: falhas não interrompem o usuário */
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [term]);

  const groups = useMemo(() => [...(localGroup ? [localGroup] : []), ...remote], [localGroup, remote]);
  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  useEffect(() => setCursor(0), [term]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, []);

  const go = (item: Item) => {
    setOpen(false);
    setTerm("");
    router.push(item.href);
  };

  let index = -1;

  return (
    <div ref={boxRef} className="relative w-full max-w-2xl">
      <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        ref={inputRef}
        value={term}
        onChange={(e) => {
          setTerm(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setCursor((c) => Math.min(c + 1, flat.length - 1));
          }
          if (e.key === "ArrowUp") {
            e.preventDefault();
            setCursor((c) => Math.max(c - 1, 0));
          }
          if (e.key === "Enter" && flat[cursor]) go(flat[cursor]);
        }}
        placeholder="Buscar telas, servidores, processos..."
        className="h-10 w-full rounded-full border border-input bg-muted/60 pl-10 pr-16 text-[13.5px] placeholder:text-muted-foreground focus:bg-card focus:outline-none focus:ring-2 focus:ring-ring/30"
        aria-label="Pesquisa global"
      />
      <kbd className="pointer-events-none absolute right-3.5 top-1/2 hidden -translate-y-1/2 rounded border bg-card px-1.5 text-[10px] text-muted-foreground md:block">
        Ctrl K
      </kbd>

      {open && term.trim().length >= 2 && (
        <div className="absolute left-0 right-0 top-11 z-40 max-h-[70vh] overflow-y-auto rounded-md border bg-popover shadow-lg thin-scroll">
          {groups.map((g) => (
            <div key={g.key} className="border-b last:border-0">
              <div className="section-label px-3 pb-1 pt-2">{g.label}</div>
              {g.items.map((item) => {
                index += 1;
                const i = index;
                return (
                  <button
                    key={`${g.key}-${item.id}`}
                    type="button"
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => go(item)}
                    className={cn(
                      "flex w-full items-center gap-2.5 px-3 py-1.5 text-left",
                      cursor === i ? "bg-primary-soft" : "hover:bg-muted",
                    )}
                  >
                    <LayoutGrid className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{item.title}</span>
                      {item.subtitle && <span className="block truncate text-2xs text-muted-foreground">{item.subtitle}</span>}
                    </span>
                    {cursor === i && <CornerDownLeft className="h-3.5 w-3.5 text-muted-foreground" />}
                  </button>
                );
              })}
            </div>
          ))}
          {!groups.length && !loading && (
            <div className="px-3 py-4 text-center text-xs text-muted-foreground">Nenhum resultado para “{term}”.</div>
          )}
          {loading && (
            <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Pesquisando...
            </div>
          )}
          <div className="border-t bg-muted/50 px-3 py-1.5 text-2xs text-muted-foreground">
            Segurados, CPF, matrícula, benefícios, processos, pensionistas e instituidores passam a ser
            pesquisáveis com os módulos das Fases 2 a 4.
          </div>
        </div>
      )}
    </div>
  );
}
