import { Construction, FlaskConical } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Selo obrigatório para qualquer dado de demonstração. */
export function DemoBadge({ className, title }: { className?: string; title?: string }) {
  return (
    <Badge variant="demo" className={className} title={title ?? "Dado de demonstração — não representa informação real"}>
      <FlaskConical className="h-3 w-3" /> DEMO
    </Badge>
  );
}

export function SourceBadge({ source, note }: { source: Source; note?: string }) {
  if (source === "demo") return <DemoBadge title={note} />;
  if (source === "indisponivel")
    return (
      <Badge variant="neutral" title={note}>
        <Construction className="h-3 w-3" /> Em desenvolvimento
      </Badge>
    );
  return null;
}

const STATUS_VARIANT: Record<string, "success" | "neutral" | "warning" | "critical" | "info" | "default"> = {
  ATIVO: "success", ATIVA: "success", ABERTO: "info", ABERTA: "info", FECHADO: "neutral", FECHADA: "neutral",
  INATIVO: "neutral", INATIVA: "neutral", BLOQUEADO: "critical", RESOLVIDO: "success", DESCARTADO: "neutral",
  PENDENTE: "warning",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <Badge variant={STATUS_VARIANT[status] ?? "default"}>{label ?? status}</Badge>;
}

export function InDevelopmentNote({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-xs text-muted-foreground", className)}>
      <Construction className="h-4 w-4 shrink-0" />
      <span>{text}</span>
    </div>
  );
}
