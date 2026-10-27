import { Badge } from "@/components/ui/badge";
import type { ProcessRow } from "@/lib/types";

/** Situação do prazo: atrasado (vermelho), até 5 dias (amarelo), em dia (verde) ou congelado (sobrestado). */
export function DeadlineBadge({ p }: { p: ProcessRow }) {
  if (!p.prazo || p.prazo.dias_restantes === null) return null;
  const unit = p.business_days ? "dia(s) úteis" : "dia(s)";
  if (p.status === "SOBRESTADO") return <Badge variant="neutral">Prazo suspenso</Badge>;
  const d = p.prazo.dias_restantes;
  if (d < 0) return <Badge variant="critical">Atrasado {Math.abs(d)} {unit}</Badge>;
  if (d <= 5) return <Badge variant="warning">{d === 0 ? "Vence hoje" : `Faltam ${d} ${unit}`}</Badge>;
  return <Badge variant="success">Faltam {d} {unit}</Badge>;
}

export function StatusBadge({ p }: { p: ProcessRow }) {
  const variant = p.status === "EM_TRAMITACAO" ? "default" : p.status === "SOBRESTADO" ? "warning" : "neutral";
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Badge variant={variant}>{p.status_display}</Badge>
      {p.pending_receipt && <Badge variant="info">A receber</Badge>}
      {p.priority !== "NORMAL" && <Badge variant="demo">Prioridade</Badge>}
    </span>
  );
}
