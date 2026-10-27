"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CheckCircle2, Loader2, RefreshCw } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ErrorState } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { SeverityBadge, SeverityIcon } from "@/components/shared/severity";
import { DemoBadge, StatusBadge } from "@/components/shared/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox, Label, Select, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Alert } from "@/lib/types";
import { cn } from "@/lib/utils";

type Summary = { total: number; CRITICO: number; ATENCAO: number; INFORMATIVO: number; demo: number };

export default function AlertsPage() {
  return (
    <RequirePermission module="alertas">
      <Alerts />
    </RequirePermission>
  );
}

function Alerts() {
  const { can } = useSession();
  const canEdit = can("alertas", "editar");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("ABERTO");
  const [page, setPage] = useState(1);
  const [running, setRunning] = useState(false);
  const [resolving, setResolving] = useState<Alert | null>(null);

  const listKey = `alerts${qs({ severity, status, page })}`;
  const { data, error, isLoading, mutate } = useSWR<Paginated<Alert>>(listKey, fetcher);
  const { data: summary, mutate: mutateSummary } = useSWR<Summary>("alerts/summary", fetcher);

  const runChecks = async () => {
    setRunning(true);
    try {
      const r = await api<{ criados: number; mantidos: number; resolvidos: number }>("alerts/run-checks", { method: "POST" });
      toast.success(`Verificação concluída: ${r.criados} novo(s), ${r.resolvidos} resolvido(s) automaticamente.`);
      mutate();
      mutateSummary();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const tiles: { key: string; label: string; value?: number; tone: string }[] = [
    { key: "", label: "Abertos", value: summary?.total, tone: "text-foreground" },
    { key: "CRITICO", label: "Críticos", value: summary?.CRITICO, tone: "text-critical" },
    { key: "ATENCAO", label: "Atenção", value: summary?.ATENCAO, tone: "text-warning" },
    { key: "INFORMATIVO", label: "Informativos", value: summary?.INFORMATIVO, tone: "text-info" },
  ];

  return (
    <>
      <PageHeader
        title="Central de Alertas"
        description="Inconsistências detectadas automaticamente a cada 30 minutos e sob demanda."
        breadcrumb={[{ label: "Painel Geral", href: "/" }, { label: "Central de Alertas" }]}
        actions={
          canEdit && (
            <Button variant="outline" size="sm" onClick={runChecks} disabled={running}>
              {running ? <Loader2 className="animate-spin" /> : <RefreshCw />} Executar verificações
            </Button>
          )
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {tiles.map((t) => (
          <button
            key={t.label}
            type="button"
            onClick={() => { setSeverity(t.key); setStatus("ABERTO"); setPage(1); }}
            className={cn(
              "rounded-lg border bg-card px-4 py-3 text-left shadow-card transition-colors hover:border-primary/40",
              severity === t.key && status === "ABERTO" && "border-primary ring-1 ring-primary/30",
            )}
          >
            <div className="section-label">{t.label}</div>
            <div className={cn("mt-1 text-xl font-semibold tabular", t.tone)}>{t.value ?? "—"}</div>
          </button>
        ))}
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Label htmlFor="f-status">Situação</Label>
            <Select id="f-status" className="w-36" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="ABERTO">Abertos</option>
              <option value="RESOLVIDO">Resolvidos</option>
              <option value="DESCARTADO">Descartados</option>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="f-sev">Classificação</Label>
            <Select id="f-sev" className="w-36" value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }}>
              <option value="">Todas</option>
              <option value="CRITICO">Crítico</option>
              <option value="ATENCAO">Atenção</option>
              <option value="INFORMATIVO">Informativo</option>
            </Select>
          </div>
          {summary && summary.demo > 0 && (
            <span className="ml-auto flex items-center gap-1.5 text-2xs text-muted-foreground">
              <DemoBadge /> {summary.demo} alerta(s) de demonstração (python manage.py seed_demo --remove)
            </span>
          )}
        </div>

        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <ul className="divide-y">
          {isLoading && Array.from({ length: 4 }).map((_, i) => (
            <li key={i} className="px-4 py-3"><Skeleton className="h-10 w-full" /></li>
          ))}
          {data?.results.map((a) => (
            <li key={a.id} className="flex items-start gap-3 px-4 py-3">
              <SeverityIcon severity={a.severity} className="mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[13px] font-medium">{a.title}</span>
                  <SeverityBadge severity={a.severity} />
                  {a.is_demo && <DemoBadge />}
                  {a.status !== "ABERTO" && <StatusBadge status={a.status} label={a.status_display} />}
                </div>
                {a.message && <p className="mt-0.5 text-xs text-muted-foreground">{a.message}</p>}
                <p className="mt-1 text-2xs text-muted-foreground">
                  Detectado em {formatDateTime(a.detected_at)} · Módulo {a.module || "—"}
                  {a.resolved_at && ` · Encerrado em ${formatDateTime(a.resolved_at)}${a.resolved_by_name ? ` por ${a.resolved_by_name}` : ""}`}
                </p>
                {a.resolution_note && <p className="mt-1 text-2xs italic text-muted-foreground">“{a.resolution_note}”</p>}
              </div>
              <div className="flex shrink-0 gap-2">
                {a.link && (
                  <Button variant="outline" size="sm" asChild>
                    <a href={a.link}>Abrir</a>
                  </Button>
                )}
                {canEdit && a.status === "ABERTO" && (
                  <Button variant="outline" size="sm" onClick={() => setResolving(a)}>
                    <CheckCircle2 /> Encerrar
                  </Button>
                )}
              </div>
            </li>
          ))}
          {data && data.results.length === 0 && (
            <li className="px-4 py-10 text-center text-xs text-muted-foreground">Nenhum alerta para os filtros selecionados.</li>
          )}
        </ul>
        {data && data.num_pages > 1 && (
          <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />
        )}
      </Card>

      <ResolveDialog
        alert={resolving}
        onClose={() => setResolving(null)}
        onDone={() => { mutate(); mutateSummary(); }}
      />
    </>
  );
}

function ResolveDialog({ alert, onClose, onDone }: { alert: Alert | null; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [discard, setDiscard] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!alert) return;
    setBusy(true);
    try {
      await api(`alerts/${alert.id}/resolve`, { method: "POST", body: { note, discard } });
      toast.success("Alerta encerrado.");
      setNote("");
      setDiscard(false);
      onDone();
      onClose();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={Boolean(alert)} onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Encerrar alerta</DialogTitle>
          <DialogDescription>{alert?.title}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <div>
            <Label htmlFor="note">Observação (registrada na auditoria)</Label>
            <Textarea id="note" className="mt-1" value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
          </div>
          <label className="flex items-center gap-2 text-xs">
            <Checkbox checked={discard} onChange={(e) => setDiscard(e.target.checked)} />
            Descartar (não procede), em vez de marcar como resolvido
          </label>
          <p className="text-2xs text-muted-foreground">
            Alertas automáticos reaparecem na próxima verificação se a inconsistência continuar existindo.
          </p>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={busy || note.trim().length < 5}>
            {busy && <Loader2 className="animate-spin" />} Confirmar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
