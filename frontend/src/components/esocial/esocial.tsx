"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CheckCircle2, Download, FileUp, Loader2, Lock, RefreshCw, Repeat, Search, XCircle } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox, Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, download, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCPF, formatDateTime } from "@/lib/format";
import type { PayrollRun } from "@/lib/types";

export type EventStatus = "PENDENTE" | "VALIDADO" | "EXPORTADO" | "ACEITO" | "REJEITADO" | "SUBSTITUIDO";
type EventRow = {
  id: string; event_type: string; event_type_display: string; event_id: string; status: EventStatus; status_display: string;
  retification: boolean; replaces: string | null; replaces_event_id: string; replaced: boolean; reference: string; period: string;
  cpf: string; pendencies: string[]; layout_version: string; environment: number; exported_at: string | null; receipt: string;
  return_code: string; return_message: string; returned_at: string | null; created_at: string;
};
type LogRow = { id: string; event: string; event_id: string; event_type: string; event_reference: string; action: string; detail: string; user_name: string; created_at: string };
type EventDetail = EventRow & { xml: string; xsd_disponivel: boolean; logs: LogRow[] };

const TYPES = ["S-2400", "S-2410", "S-2420", "S-1010", "S-1207", "S-1210", "S-1299"];
const STATUS_VARIANT: Record<EventStatus, "default" | "info" | "success" | "warning" | "neutral" | "critical"> = {
  PENDENTE: "warning", VALIDADO: "info", EXPORTADO: "default", ACEITO: "success", REJEITADO: "critical", SUBSTITUIDO: "neutral",
};
const STATUS_LABEL: Record<EventStatus, string> = {
  PENDENTE: "Com pendências", VALIDADO: "Pronto", EXPORTADO: "Aguardando retorno", ACEITO: "Aceito", REJEITADO: "Rejeitado", SUBSTITUIDO: "Substituído",
};

const NOTE = "O SIST gera e confere os XMLs. Com o certificado digital do órgão cadastrado, transmita direto em eSocial › Transmissão (o retorno de cada evento é buscado no eSocial). Sem certificado, exporte os eventos prontos, transmita pelo seu programa e importe o arquivo de retorno (ou informe o recibo).";

// ------------------------------------------------------------------ geração
function useGenerators(onDone: () => void) {
  const [busy, setBusy] = useState("");
  const run = async (key: string, path: string, body?: Record<string, unknown>) => {
    setBusy(key);
    try {
      const r = await api<Record<string, number> | EventRow>(path, { method: "POST", body });
      const counts = Object.entries(r).filter(([, v]) => typeof v === "number").map(([k, v]) => `${k}: ${v}`);
      toast.success(counts.length ? `Eventos gerados — ${counts.join(" · ")}` : "Evento gerado.");
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
      throw err;
    } finally {
      setBusy("");
    }
  };
  return { busy, run };
}

function GenerateBar({ kinds, onDone }: { kinds: ("cadastrais" | "rubricas" | "folha" | "fechamento")[]; onDone: () => void }) {
  const { can } = useSession();
  const { busy, run } = useGenerators(onDone);
  const [dialog, setDialog] = useState<"folha" | "fechamento" | null>(null);
  const runs = useSWR<Paginated<PayrollRun>>(dialog === "folha" ? "folha/folhas?situacoes=FECHADA,PAGA&page_size=50" : null, fetcher);
  const canReg = can("esocial.s2400", "incluir") || can("esocial.s2410", "incluir");
  return (
    <div className="flex flex-wrap gap-2">
      {kinds.includes("cadastrais") && canReg && (
        <Button onClick={() => run("cad", "esocial/eventos/generate-registrations").catch(() => undefined)} disabled={!!busy}>
          {busy === "cad" ? <Loader2 className="animate-spin" /> : <RefreshCw />} Gerar S-2400 / S-2410 / S-2420
        </Button>
      )}
      {kinds.includes("rubricas") && can("esocial.s1207", "incluir") && (
        <Button variant="outline" onClick={() => run("rub", "esocial/eventos/generate-rubrics").catch(() => undefined)} disabled={!!busy}>
          {busy === "rub" ? <Loader2 className="animate-spin" /> : <RefreshCw />} Gerar S-1010 (rubricas)
        </Button>
      )}
      {kinds.includes("folha") && can("esocial.s1207", "incluir") && (
        <Button variant="outline" onClick={() => setDialog("folha")} disabled={!!busy}><RefreshCw /> Gerar S-1207 / S-1210 da folha</Button>
      )}
      {kinds.includes("fechamento") && can("esocial.s1207", "aprovar") && (
        <Button variant="outline" onClick={() => setDialog("fechamento")} disabled={!!busy}><Lock /> Fechar período (S-1299)</Button>
      )}
      {dialog === "folha" && (
        <FormDialog title="Eventos periódicos da folha" size="sm" onClose={() => setDialog(null)}
          description="S-1207 (benefícios) para folha FECHADA; S-1210 (pagamentos) quando a folha estiver PAGA."
          fields={[{ name: "run", label: "Folha", type: "select", required: true, wide: true,
            options: (runs.data?.results ?? []).map((r) => ({ value: r.id, label: `${r.kind === "DECIMO" ? "13º" : "Mensal"} ${String(r.month).padStart(2, "0")}/${r.year} — ${r.folha} (${r.status_display})` })) }]}
          submitLabel="Gerar" submit={async (body) => run("folha", "esocial/eventos/generate-payroll", body)} />
      )}
      {dialog === "fechamento" && (
        <FormDialog title="Fechamento dos eventos periódicos (S-1299)" size="sm" onClose={() => setDialog(null)}
          description="Só é permitido depois que todos os S-1207 e S-1210 do período forem aceitos."
          fields={[{ name: "period", label: "Período (AAAA-MM, ou AAAA para o 13º)", required: true, wide: true }]}
          initial={{ period: new Date().toISOString().slice(0, 7) }}
          submitLabel="Gerar fechamento" submit={async (body) => run("fech", "esocial/eventos/close-period", body)} />
      )}
    </div>
  );
}

// ------------------------------------------------------------------ lista de eventos
type ListProps = {
  module: string; title: string; description: string; tipos?: string[]; situacoes?: EventStatus[];
  generate?: ("cadastrais" | "rubricas" | "folha" | "fechamento")[]; importReturn?: boolean;
};

export function EventsPage(props: ListProps) {
  return <RequirePermission module={props.module}><Events {...props} /></RequirePermission>;
}

function Events({ title, description, tipos, situacoes, generate, importReturn }: ListProps) {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const key = `esocial/eventos${qs({
    search: debounced, page, event_type: type || undefined, tipos: type ? undefined : tipos?.join(","),
    status: status || undefined, situacoes: status ? undefined : situacoes?.join(","),
  })}`;
  const { data, error, isLoading, mutate } = useSWR<Paginated<EventRow>>(key, fetcher, { keepPreviousData: true });
  const exportable = data?.results.filter((e) => e.status === "VALIDADO" || e.status === "EXPORTADO") ?? [];
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const doExport = async () => {
    setExporting(true);
    try {
      await download("esocial/eventos/export", "esocial.zip", { ids: [...sel] });
      toast.success(`${sel.size} evento(s) exportado(s). Assine e transmita pelo programa transmissor.`);
      setSel(new Set());
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <PageHeader title={title} description={description} breadcrumb={[{ label: "eSocial RPPS" }, { label: title }]}
        actions={generate && <GenerateBar kinds={generate} onDone={() => mutate()} />} />
      <Card className="mb-3 border-info/30 bg-info/5 px-4 py-2 text-xs">{NOTE}</Card>
      {importReturn && <ImportReturn onDone={() => mutate()} />}
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="relative w-full max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome, CPF, Id ou recibo" className="pl-8" />
          </div>
          <Select className="w-36" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} aria-label="Evento">
            <option value="">{tipos ? "Eventos desta tela" : "Todos os eventos"}</option>
            {(tipos ?? TYPES).map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
          {!situacoes && (
            <Select className="w-44" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
              <option value="">Todas as situações</option>
              {(Object.keys(STATUS_LABEL) as EventStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </Select>
          )}
          <div className="ml-auto flex items-center gap-2">
            {exportable.length > 0 && can("esocial.eventos", "exportar") && (
              <Button size="sm" variant="ghost" onClick={() => setSel(new Set(exportable.map((e) => e.id)))}>Selecionar prontos ({exportable.length})</Button>
            )}
            {can("esocial.eventos", "exportar") && (
              <Button size="sm" onClick={doExport} disabled={!sel.size || exporting}>{exporting ? <Loader2 className="animate-spin" /> : <Download />} Exportar XML ({sel.size})</Button>
            )}
          </div>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead className="w-8" /><TableHead>Evento</TableHead><TableHead>Referência</TableHead><TableHead>Período</TableHead><TableHead>Gerado em</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={6} />}
            {data?.results.map((e) => (
              <TableRow key={e.id} className="cursor-pointer" onClick={() => setOpen(e.id)}>
                <TableCell onClick={(ev) => ev.stopPropagation()}>
                  {(e.status === "VALIDADO" || e.status === "EXPORTADO") && <Checkbox checked={sel.has(e.id)} onChange={() => toggle(e.id)} aria-label="Selecionar" />}
                </TableCell>
                <TableCell className="font-mono text-xs font-semibold">{e.event_type}{e.retification && <Badge variant="neutral" className="ml-1">retificação</Badge>}</TableCell>
                <TableCell><div className="font-medium text-primary">{e.reference}</div>
                  {e.status === "PENDENTE" && <div className="text-2xs text-warning">{e.pendencies[0]}{e.pendencies.length > 1 ? ` (+${e.pendencies.length - 1})` : ""}</div>}
                  {e.status === "REJEITADO" && <div className="text-2xs text-critical">{e.return_code} {e.return_message}</div>}
                  {e.receipt && <div className="text-2xs text-muted-foreground">recibo {e.receipt}</div>}</TableCell>
                <TableCell className="text-xs">{e.period || "—"}</TableCell>
                <TableCell className="text-xs">{formatDateTime(e.created_at)}</TableCell>
                <TableCell><Badge variant={STATUS_VARIANT[e.status]}>{STATUS_LABEL[e.status]}</Badge></TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum evento." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {open && <EventDialog id={open} onClose={() => setOpen(null)} onChanged={() => mutate()} onOpen={setOpen} />}
    </>
  );
}

function EventDialog({ id, onClose, onChanged, onOpen }: { id: string; onClose: () => void; onChanged: () => void; onOpen: (id: string) => void }) {
  const { can } = useSession();
  const { data: ev, error, mutate } = useSWR<EventDetail>(`esocial/eventos/${id}`, fetcher);
  const [busy, setBusy] = useState("");
  const [ret, setRet] = useState<"ok" | "erro" | null>(null);
  const act = async (key: string, path: string, ok: string) => {
    setBusy(key);
    try {
      const r = await api<EventRow>(`esocial/eventos/${id}/${path}`, { method: "POST" });
      toast.success(ok);
      onChanged();
      if (r.id !== id) onOpen(r.id); else mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{ev ? `${ev.event_type_display}` : "Evento"}</DialogTitle>
          {ev && <DialogDescription>{ev.reference} · <Badge variant={STATUS_VARIANT[ev.status]}>{STATUS_LABEL[ev.status]}</Badge></DialogDescription>}
        </DialogHeader>
        <DialogBody className="space-y-3 text-xs">
          {error && <ErrorState error={error} />}
          {ev && <>
            <div className="grid gap-1 sm:grid-cols-2">
              <div><span className="text-muted-foreground">Id: </span><span className="font-mono">{ev.event_id}</span></div>
              <div><span className="text-muted-foreground">Leiaute / ambiente: </span>{ev.layout_version} · {ev.environment === 1 ? "produção" : "produção restrita"}</div>
              {ev.cpf && <div><span className="text-muted-foreground">CPF: </span>{formatCPF(ev.cpf)}</div>}
              {ev.receipt && <div><span className="text-muted-foreground">Recibo: </span>{ev.receipt}</div>}
              {ev.replaces_event_id && <div className="sm:col-span-2"><span className="text-muted-foreground">Substitui: </span><button className="font-mono text-primary hover:underline" onClick={() => ev.replaces && onOpen(ev.replaces)}>{ev.replaces_event_id}</button></div>}
              <div className="sm:col-span-2 text-muted-foreground">{ev.xsd_disponivel ? "Validado também contra o XSD oficial." : "XSD oficial não instalado: conferidos só os campos obrigatórios (copie os .xsd para backend/apps/esocial/xsd/)."}</div>
            </div>
            {ev.pendencies.length > 0 && (
              <div className="rounded border border-warning/40 bg-warning/5 px-3 py-2">
                <div className="mb-1 font-medium">Pendências — corrija o cadastro e clique em “Revalidar”</div>
                <ul className="list-disc pl-5">{ev.pendencies.map((p) => <li key={p}>{p}</li>)}</ul>
              </div>
            )}
            {ev.status === "REJEITADO" && (
              <div className="rounded border border-critical/40 bg-critical/5 px-3 py-2"><b>Rejeição {ev.return_code}:</b> {ev.return_message}</div>
            )}
            <div className="flex flex-wrap gap-2">
              {(ev.status === "PENDENTE" || ev.status === "VALIDADO") && ev.event_type !== "S-1299" && can("esocial.pendencias", "editar") && (
                <Button size="sm" variant="outline" onClick={() => act("rev", "revalidate", "Evento remontado com os dados atuais.")} disabled={!!busy}><RefreshCw /> Revalidar</Button>
              )}
              {ev.status === "EXPORTADO" && can("esocial.retornos", "incluir") && <>
                <Button size="sm" variant="outline" onClick={() => setRet("ok")}><CheckCircle2 /> Informar aceite (recibo)</Button>
                <Button size="sm" variant="outline" onClick={() => setRet("erro")}><XCircle /> Informar rejeição</Button>
              </>}
              {ev.status === "REJEITADO" && !ev.replaced && can("esocial.rejeicoes", "editar") && (
                <Button size="sm" variant="outline" onClick={() => act("rep", "replace", "Novo evento gerado com os dados corrigidos.")} disabled={!!busy}><Repeat /> Gerar evento corrigido</Button>
              )}
              {ev.status === "ACEITO" && !ev.replaced && !["S-1010", "S-1299"].includes(ev.event_type) && can("esocial.rejeicoes", "editar") && (
                <Button size="sm" variant="outline" onClick={() => act("rep", "replace", "Retificação gerada (indRetif = 2).")} disabled={!!busy}><Repeat /> Retificar</Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => download(`esocial/eventos/${id}/xml`, `${ev.event_id}.xml`).catch((e) => toast.error((e as Error).message))}><Download /> Baixar XML</Button>
            </div>
            <details>
              <summary className="cursor-pointer font-medium">XML do evento (não assinado)</summary>
              <pre className="mt-1 max-h-80 overflow-auto rounded bg-muted p-2 font-mono text-[11px] leading-snug">{ev.xml}</pre>
            </details>
            <div>
              <div className="section-label mb-1">Histórico</div>
              <ul className="space-y-1">{ev.logs.map((l) => <li key={l.id}>{formatDateTime(l.created_at)} — <b>{l.action}</b>{l.detail ? `: ${l.detail}` : ""} <span className="text-muted-foreground">({l.user_name || "Sistema"})</span></li>)}</ul>
            </div>
          </>}
        </DialogBody>
      </DialogContent>
      {ret && ev && (
        <FormDialog size="sm" title={ret === "ok" ? "Evento aceito pelo eSocial" : "Evento rejeitado pelo eSocial"} onClose={() => setRet(null)}
          description="Copie as informações do retorno do programa transmissor."
          fields={ret === "ok"
            ? [{ name: "receipt", label: "Número do recibo", required: true, wide: true }]
            : [{ name: "code", label: "Código do erro", wide: true }, { name: "message", label: "Mensagem", type: "textarea", required: true }]}
          submit={async (body) => {
            await api(`esocial/eventos/${id}/return`, { method: "POST", body: { ...body, accepted: ret === "ok" } });
            toast.success("Retorno registrado.");
            mutate();
            onChanged();
          }} />
      )}
    </Dialog>
  );
}

function ImportReturn({ onDone }: { onDone: () => void }) {
  const { can } = useSession();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  if (!can("esocial.retornos", "incluir")) return null;
  const send = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/backend/esocial/eventos/import-return", { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Falha ao importar o retorno.");
      toast.success(`Retorno importado: ${body.registrados} de ${body.eventos_no_arquivo} evento(s) registrados${body.nao_localizados?.length ? `; ${body.nao_localizados.length} não localizado(s) ou já com retorno` : ""}.`);
      setFile(null);
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="mb-3 flex flex-wrap items-end gap-3 px-4 py-3">
      <FormField label="Arquivo de retorno do lote (XML)" htmlFor="ret-file" className="min-w-64 flex-1"
        hint="Arquivo 'retornoProcessamentoLoteEventos' devolvido pelo eSocial ao programa transmissor.">
        <Input id="ret-file" type="file" accept=".xml,text/xml,application/xml" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </FormField>
      <Button onClick={send} disabled={!file || busy}>{busy ? <Loader2 className="animate-spin" /> : <FileUp />} Importar retorno</Button>
    </Card>
  );
}

// ------------------------------------------------------------------ painel
type Summary = { por_evento: Record<string, Record<EventStatus, number>>; xsd: Record<string, boolean> };

export function EsocialDashboard() {
  return <RequirePermission module="esocial.painel"><Dashboard /></RequirePermission>;
}

function Dashboard() {
  const { data, error, mutate } = useSWR<Summary>("esocial/eventos/summary", fetcher);
  const cols: EventStatus[] = ["PENDENTE", "VALIDADO", "EXPORTADO", "ACEITO", "REJEITADO"];
  const total = (s: EventStatus) => (data ? Object.values(data.por_evento).reduce((a, r) => a + (r[s] ?? 0), 0) : 0);
  const xsdCount = data ? Object.values(data.xsd).filter(Boolean).length : 0;
  return (
    <>
      <PageHeader title="Painel eSocial" breadcrumb={[{ label: "eSocial RPPS" }, { label: "Painel" }]}
        description="Eventos do RPPS: S-2400 (beneficiário), S-2410 (benefício), S-2420 (término), S-1010 (rubricas), S-1207 (benefícios da folha), S-1210 (pagamentos) e S-1299 (fechamento)."
        actions={<GenerateBar kinds={["cadastrais", "rubricas", "folha", "fechamento"]} onDone={() => mutate()} />} />
      <Card className="mb-3 border-info/30 bg-info/5 px-4 py-2 text-xs">{NOTE}</Card>
      {error && <ErrorState error={error} />}
      <div className="mb-3 grid gap-3 sm:grid-cols-5">
        {cols.map((s) => (
          <Card key={s} className="px-4 py-3">
            <div className="text-2xs uppercase tracking-wide text-muted-foreground">{STATUS_LABEL[s]}</div>
            <div className="tabular text-lg font-semibold">{total(s)}</div>
          </Card>
        ))}
      </div>
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Evento</TableHead>{cols.map((s) => <TableHead key={s} className="text-right">{STATUS_LABEL[s]}</TableHead>)}<TableHead>XSD oficial</TableHead></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={7} />}
            {data && TYPES.map((t) => (
              <TableRow key={t}>
                <TableCell className="font-mono text-xs font-semibold">{t}</TableCell>
                {cols.map((s) => <TableCell key={s} className="text-right tabular">{data.por_evento[t]?.[s] || "—"}</TableCell>)}
                <TableCell>{data.xsd[t] ? <Badge variant="success">instalado</Badge> : <Badge variant="neutral">não instalado</Badge>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      {data && xsdCount === 0 && (
        <p className="mt-2 text-2xs text-muted-foreground">
          Para validar contra os esquemas oficiais, baixe o pacote de leiautes S-1.3 no portal do eSocial e copie os arquivos .xsd para <code>backend/apps/esocial/xsd/</code>.
        </p>
      )}
    </>
  );
}

// ------------------------------------------------------------------ histórico
export function HistoryPage() {
  return <RequirePermission module="esocial.historico"><History /></RequirePermission>;
}

function History() {
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const { data, error } = useSWR<Paginated<LogRow>>(`esocial/eventos/history${qs({ page })}`, fetcher);
  return (
    <>
      <PageHeader title="Histórico de envios" breadcrumb={[{ label: "eSocial RPPS" }, { label: "Histórico" }]}
        description="Tudo o que aconteceu com os eventos: geração, revalidação, exportação, aceite, rejeição e substituição." />
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Data/hora</TableHead><TableHead>Ação</TableHead><TableHead>Evento</TableHead><TableHead>Detalhe</TableHead><TableHead>Usuário</TableHead></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={5} />}
            {data?.results.map((l) => (
              <TableRow key={l.id} className="cursor-pointer" onClick={() => setOpen(l.event)}>
                <TableCell className="text-xs">{formatDateTime(l.created_at)}</TableCell>
                <TableCell><Badge variant="neutral">{l.action}</Badge></TableCell>
                <TableCell className="text-xs"><span className="font-mono font-semibold">{l.event_type}</span> {l.event_reference}</TableCell>
                <TableCell className="text-xs">{l.detail}</TableCell>
                <TableCell className="text-xs">{l.user_name || "Sistema"}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum registro." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {open && <EventDialog id={open} onClose={() => setOpen(null)} onChanged={() => undefined} onOpen={setOpen} />}
    </>
  );
}

