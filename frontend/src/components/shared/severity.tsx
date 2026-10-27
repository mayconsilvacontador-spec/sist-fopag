import Link from "next/link";
import { AlertOctagon, AlertTriangle, ChevronRight, Info } from "lucide-react";

import type { Alert, Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

import { DemoBadge } from "./status";

const STYLE: Record<Severity, { icon: typeof Info; text: string; box: string; label: string }> = {
  CRITICO: { icon: AlertOctagon, text: "text-critical", box: "border-critical-border bg-critical-soft", label: "Crítico" },
  ATENCAO: { icon: AlertTriangle, text: "text-warning", box: "border-warning-border bg-warning-soft", label: "Atenção" },
  INFORMATIVO: { icon: Info, text: "text-info", box: "border-info-border bg-info-soft", label: "Informativo" },
};

export function SeverityIcon({ severity, className }: { severity: Severity; className?: string }) {
  const S = STYLE[severity];
  const Icon = S.icon;
  return <Icon className={cn("h-4 w-4 shrink-0", S.text, className)} aria-label={S.label} />;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const S = STYLE[severity];
  return (
    <span className={cn("inline-flex items-center rounded border px-1.5 py-px text-2xs font-bold uppercase tracking-wide", S.box, S.text)}>
      {S.label}
    </span>
  );
}

/** Linha de aviso no estilo SIST-SICI: faixa lateral colorida, ícone e texto. */
export function AlertLine({ alert, compact }: { alert: Alert; compact?: boolean }) {
  const S = STYLE[alert.severity];
  const content = (
    <div
      className={cn(
        "group flex items-start gap-2.5 rounded-md border-l-[3px] border bg-card px-3",
        compact ? "py-2" : "py-2.5",
        alert.severity === "CRITICO" && "border-l-critical",
        alert.severity === "ATENCAO" && "border-l-warning",
        alert.severity === "INFORMATIVO" && "border-l-info",
        alert.link && "hover:bg-muted/60",
      )}
    >
      <SeverityIcon severity={alert.severity} className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[13px] font-medium leading-snug">{alert.title}</span>
          {alert.is_demo && <DemoBadge />}
        </div>
        {!compact && alert.message && <p className="mt-0.5 text-xs text-muted-foreground">{alert.message}</p>}
      </div>
      <span className={cn("hidden shrink-0 text-2xs font-bold uppercase sm:inline", S.text)}>{S.label}</span>
      {alert.link && <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground group-hover:text-foreground" />}
    </div>
  );
  return alert.link ? <Link href={alert.link}>{content}</Link> : content;
}
