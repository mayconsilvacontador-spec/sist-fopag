import { cn } from "@/lib/utils";

/** Símbolo do SIST (letra S). Usado no login, no portal do segurado e quando não há brasão cadastrado. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-[22px] font-black italic leading-none text-white", className)}
      aria-hidden="true">
      S
    </span>
  );
}

/** Brasão do município contratante (quando cadastrado) ou o símbolo do SIST. */
export function Crest({ url, className }: { url?: string | null; className?: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="Brasão" className={cn("h-10 w-10 shrink-0 object-contain", className)} />;
  }
  return <LogoMark className={className} />;
}

/** "SIST FOPAG" com a sigla da instituição embaixo (padrão SIST-SIFAB). */
export function Logo({ collapsed, crestUrl, dark, subtitle }: { collapsed?: boolean; crestUrl?: string | null; dark?: boolean; subtitle?: string }) {
  return (
    <div className="flex items-center gap-2.5 overflow-hidden">
      <Crest url={crestUrl} />
      {!collapsed && (
        <div className="min-w-0 leading-tight">
          <div className="flex items-baseline gap-1.5">
            <span className={cn("text-[11px] font-medium uppercase tracking-[0.2em]", dark ? "text-white/70" : "text-muted-foreground")}>Sist</span>
            <span className={cn("text-[17px] font-bold tracking-wide", dark ? "text-white" : "text-primary")}>FOPAG</span>
          </div>
          <div className={cn("truncate text-[10.5px] uppercase tracking-wide", dark ? "text-white/70" : "text-muted-foreground")}>
            {subtitle || "Sistema Integrado de Gestão de RPPS"}
          </div>
        </div>
      )}
    </div>
  );
}
