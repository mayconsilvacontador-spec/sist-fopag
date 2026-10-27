"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Calculator, CheckCircle2, Download, Loader2, Lock, Search, Unlock, Wallet } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox, Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCPF, formatCurrency, formatDateTime, formatInt } from "@/lib/format";
import type { PayrollEntryRow, PayrollRun } from "@/lib/types";

import { PayslipDialog } from "./payslip";
import { RUN_VARIANT } from "./runs";

const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

export function downloadCsv(name: string, header: string[], rows: (string | number)[][]) {
  const esc = (v: string | number) => {
    const s = String(v ?? "");
    return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = "﻿" + [header, ...rows].map((r) => r.map(esc).join(";")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const br = (v: string) => v.replace(".", ",");

export function RunDetail({ id }: { id: string }) {
  return (
    <RequirePermission module="folha.folha_mensal">
      <Detail id={id} />
    </RequirePermission>
  );
}

function Detail({ id }: { id: string }) {
  const { can } = useSession();
  const { data: run, error, mutate } = useSWR<PayrollRun>(`folha/folhas/${id}`, fetcher);
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState<"close" | "reopen" | null>(null);
  const [paying, setPaying] = useState(false);
  const [tab, setTab] = useState("contracheques");
  useEffect(() => {
    const aba = new URLSearchParams(window.location.search).get("aba");
    if (aba) setTab(aba);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!run) return <div className="p-6 text-xs text-muted-foreground"><Loader2 className="mr-2 inline animate-spin" />Carregando…</div>;

  const act = async (what: string, path: string, body?: Record<string, unknown>, ok?: string) => {
    setBusy(what);
    try {
      await api(`folha/folhas/${id}/${path}`, { method: "POST", body });
      toast.success(ok ?? "Feito.");
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
      throw err;
    } finally {
      setBusy("");
    }
  };
  const editable = ["ABERTA", "CALCULADA", "CONFERIDA"].includes(run.status);
  const calcPerm = run.kind === "DECIMO" ? can("folha.decimo_terceiro", "calcular") : can("folha.calculo", "calcular");
  const t = run.totals ?? {};
  const title = `${run.kind === "DECIMO" ? "13º" : "Folha"} ${MONTHS[run.month - 1]}/${run.year} — ${run.folha}`;

  return (
    <>
      <PageHeader title={title}
        description={<>{run.folha_name} · <Badge variant={RUN_VARIANT[run.status]}>{run.status_display}</Badge>
          {run.calculated_at && <> · calculada em {formatDateTime(run.calculated_at)}</>}
          {run.checked_by_name && <> · conferida por {run.checked_by_name}</>}
          {run.closed_by_name && <> · fechada por {run.closed_by_name}</>}
          {run.payment_date && <> · paga em {new Date(run.payment_date + "T12:00").toLocaleDateString("pt-BR")}</>}</>}
        breadcrumb={[{ label: "Folha de Benefícios" }, { label: "Folha Mensal", href: "/folha/folha-mensal" }, { label: title }]}
        actions={
          <div className="flex flex-wrap gap-2">
            {editable && calcPerm && (
              <Button onClick={() => act("calc", "calculate", undefined, "Folha calculada.").catch(() => undefined)} disabled={!!busy}>
                {busy === "calc" ? <Loader2 className="animate-spin" /> : <Calculator />} {run.status === "ABERTA" ? "Calcular" : "Recalcular"}
              </Button>
            )}
            {run.status === "CALCULADA" && can("folha.conferencia", "aprovar") && (
              <Button variant="outline" onClick={() => act("check", "check", undefined, "Folha conferida.").catch(() => undefined)} disabled={!!busy}>
                <CheckCircle2 /> Marcar como conferida
              </Button>
            )}
            {run.status === "CONFERIDA" && can("folha.fechamento", "fechar") && (
              <Button variant="outline" onClick={() => setConfirm("close")} disabled={!!busy}><Lock /> Fechar folha</Button>
            )}
            {run.status === "FECHADA" && can("folha.fechamento", "fechar") && (
              <Button variant="outline" onClick={() => setPaying(true)} disabled={!!busy}><Wallet /> Registrar pagamento</Button>
            )}
            {run.status === "FECHADA" && can("folha.reabertura", "reabrir") && (
              <Button variant="outline" onClick={() => setConfirm("reopen")} disabled={!!busy}><Unlock /> Reabrir</Button>
            )}
          </div>
        } />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Kpi label="Benefícios" value={formatInt(t.beneficiarios ?? 0)} hint={`${t.aposentados ?? 0} aposentadorias · ${t.pensionistas ?? 0} pensões`} />
        <Kpi label="Proventos" value={formatCurrency(t.proventos ?? "0")} />
        <Kpi label="Descontos" value={formatCurrency(t.descontos ?? "0")} />
        <Kpi label="Líquido" value={formatCurrency(t.liquido ?? "0")} strong />
        <Kpi label="Pendências" value={formatInt((t.sem_conta ?? 0) + (t.liquido_negativo ?? 0))}
          hint={`${t.sem_conta ?? 0} sem conta · ${t.liquido_negativo ?? 0} líquido negativo`} warn={(t.sem_conta ?? 0) + (t.liquido_negativo ?? 0) > 0} />
      </div>
      {run.warnings.length > 0 && (
        <Card className="mb-4 border-warning/40 bg-warning/5 px-4 py-2 text-xs">
          <div className="mb-1 font-medium">Avisos do cálculo</div>
          <ul className="list-disc pl-5">{run.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </Card>
      )}
      {run.status === "ABERTA" ? (
        <Card className="p-6 text-center text-xs text-muted-foreground">Folha aberta e ainda não calculada. Clique em <b>Calcular</b>.</Card>
      ) : (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="mb-3">
            <TabsTrigger value="contracheques">Contracheques</TabsTrigger>
            <TabsTrigger value="conferencia">Conferência</TabsTrigger>
            <TabsTrigger value="resumo">Resumo por rubrica</TabsTrigger>
            <TabsTrigger value="credito">Relação de crédito</TabsTrigger>
          </TabsList>
          <TabsContent value="contracheques" className="pt-0"><Entries run={run} /></TabsContent>
          <TabsContent value="conferencia" className="pt-0"><Comparison run={run} /></TabsContent>
          <TabsContent value="resumo" className="pt-0"><Summary run={run} /></TabsContent>
          <TabsContent value="credito" className="pt-0"><Credit run={run} /></TabsContent>
        </Tabs>
      )}

      <ConfirmDialog open={confirm === "close"} onOpenChange={(v) => !v && setConfirm(null)} title="Fechar a folha?"
        description="Depois de fechada, a folha não é recalculada. As parcelas de consignações e lançamentos avançam. Para corrigir, será preciso reabrir com justificativa."
        confirmLabel="Fechar folha" onConfirm={() => act("close", "close", undefined, "Folha fechada.")} />
      <ConfirmDialog open={confirm === "reopen"} onOpenChange={(v) => !v && setConfirm(null)} title="Reabrir a folha?" requireJustification
        description="As parcelas avançadas no fechamento voltam. A reabertura fica registrada na auditoria." confirmLabel="Reabrir"
        onConfirm={(j) => act("reopen", "reopen", { justification: j }, "Folha reaberta (situação: conferida).")} />
      {paying && (
        <FormDialog title="Registrar pagamento" size="sm" description="Folha paga não pode mais ser reaberta (correções vão para a folha seguinte, como diferenças)."
          fields={[{ name: "payment_date", label: "Data do pagamento", type: "date", required: true }]}
          initial={{ payment_date: new Date().toISOString().slice(0, 10) }} submitLabel="Registrar"
          onClose={() => setPaying(false)}
          submit={async (body) => { await act("pay", "pay", body, "Pagamento registrado."); }} />
      )}
    </>
  );
}

function Kpi({ label, value, hint, strong, warn }: { label: string; value: string; hint?: string; strong?: boolean; warn?: boolean }) {
  return (
    <Card className="px-4 py-3">
      <div className="text-2xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`tabular text-lg ${strong ? "font-semibold text-primary" : "font-medium"} ${warn ? "text-warning" : ""}`}>{value}</div>
      {hint && <div className="text-2xs text-muted-foreground">{hint}</div>}
    </Card>
  );
}

function Entries({ run }: { run: PayrollRun }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [onlyWarn, setOnlyWarn] = useState(false);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const { data, error, isLoading } = useSWR<Paginated<PayrollEntryRow>>(
    `folha/folhas/${run.id}/entries${qs({ search: debounced, avisos: onlyWarn ? 1 : undefined, page })}`, fetcher,
    { keepPreviousData: true });
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Beneficiário ou CPF" className="pl-8" />
        </div>
        <label className="flex items-center gap-2 text-xs"><Checkbox checked={onlyWarn} onChange={(e) => { setOnlyWarn(e.target.checked); setPage(1); }} /> Somente com avisos</label>
      </div>
      {error && <div className="p-4"><ErrorState error={error} /></div>}
      <Table>
        <TableHeader><TableRow><TableHead>Beneficiário</TableHead><TableHead>Benefício</TableHead><TableHead className="text-right">Proventos</TableHead><TableHead className="text-right">Descontos</TableHead><TableHead className="text-right">Líquido</TableHead><TableHead /></TableRow></TableHeader>
        <TableBody>
          {isLoading && !data && <LoadingRows cols={6} />}
          {data?.results.map((e) => (
            <TableRow key={e.id} className="cursor-pointer" onClick={() => setOpen(e.id)}>
              <TableCell><div className="font-medium text-primary">{e.beneficiary_name}</div><div className="text-2xs text-muted-foreground">{e.beneficiary_cpf}</div></TableCell>
              <TableCell className="text-xs">{e.kind === "PENSAO" ? "Pensão" : "Aposentadoria"}{e.registration ? ` · ${e.registration}` : ""}</TableCell>
              <TableCell className="text-right tabular">{formatCurrency(e.gross)}</TableCell>
              <TableCell className="text-right tabular">{formatCurrency(e.discounts)}</TableCell>
              <TableCell className="text-right tabular font-medium">{formatCurrency(e.net)}</TableCell>
              <TableCell>{e.warnings.length > 0 && <Badge variant="warning" title={e.warnings.join("\n")}>{e.warnings.length} aviso(s)</Badge>}</TableCell>
            </TableRow>
          ))}
          {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum contracheque." />}
        </TableBody>
      </Table>
      {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      {open && <PayslipDialog id={open} onClose={() => setOpen(null)} />}
    </Card>
  );
}

type Cmp = {
  anterior: string | null; totais: Record<string, string | number>; totais_anterior: Record<string, string | number> | null;
  entradas: { id: string; beneficiario: string; liquido: string }[];
  saidas: { id: string; beneficiario: string; liquido: string }[];
  variacoes: { id: string; beneficiario: string; liquido: string; anterior: string; variacao_pct: string }[];
  avisos: { id: string; beneficiario: string; avisos: string[] }[];
};

function Comparison({ run }: { run: PayrollRun }) {
  const { data, error } = useSWR<Cmp>(`folha/folhas/${run.id}/comparison`, fetcher);
  const [open, setOpen] = useState<string | null>(null);
  if (error) return <ErrorState error={error} />;
  if (!data) return <Card className="p-4"><Loader2 className="animate-spin" /></Card>;
  const diff = (k: string) => data.totais_anterior ? Number(data.totais[k] ?? 0) - Number(data.totais_anterior[k] ?? 0) : null;
  return (
    <div className="space-y-3">
      <Card className="px-4 py-3 text-xs">
        {data.anterior ? (
          <div className="grid gap-2 sm:grid-cols-4">
            <div>Comparada com: <b>{data.anterior}</b></div>
            {(["proventos", "descontos", "liquido"] as const).map((k) => (
              <div key={k}>{k === "liquido" ? "Líquido" : k.charAt(0).toUpperCase() + k.slice(1)}: {formatCurrency(String(data.totais[k] ?? 0))}{" "}
                <span className={(diff(k) ?? 0) >= 0 ? "text-success" : "text-critical"}>({(diff(k) ?? 0) >= 0 ? "+" : ""}{formatCurrency(String(diff(k) ?? 0))})</span></div>
            ))}
          </div>
        ) : <span className="text-muted-foreground">Primeira folha desta massa — não há folha anterior para comparar.</span>}
      </Card>
      <div className="grid gap-3 lg:grid-cols-2">
        <ListCard title={`Entradas (${data.entradas.length})`} rows={data.entradas.map((r) => [r.beneficiario, formatCurrency(r.liquido), r.id])} onOpen={setOpen} />
        <ListCard title={`Saídas (${data.saidas.length})`} rows={data.saidas.map((r) => [r.beneficiario, formatCurrency(r.liquido), ""])} onOpen={setOpen} />
        <ListCard title={`Variação do líquido ≥ 5% (${data.variacoes.length})`}
          rows={data.variacoes.map((r) => [r.beneficiario, `${formatCurrency(r.anterior)} → ${formatCurrency(r.liquido)} (${br(r.variacao_pct)}%)`, r.id])} onOpen={setOpen} />
        <ListCard title={`Contracheques com avisos (${data.avisos.length})`} rows={data.avisos.map((r) => [r.beneficiario, r.avisos.join(" · "), r.id])} onOpen={setOpen} />
      </div>
      {open && <PayslipDialog id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function ListCard({ title, rows, onOpen }: { title: string; rows: string[][]; onOpen: (id: string) => void }) {
  return (
    <Card>
      <div className="border-b px-4 py-2 text-xs font-medium">{title}</div>
      <ul className="max-h-72 divide-y overflow-auto text-xs">
        {rows.map(([a, b, id], i) => (
          <li key={i} className={`flex justify-between gap-3 px-4 py-1.5 ${id ? "cursor-pointer hover:bg-muted/50" : ""}`} onClick={() => id && onOpen(id)}>
            <span className="font-medium">{a}</span><span className="text-right text-muted-foreground">{b}</span>
          </li>
        ))}
        {rows.length === 0 && <li className="px-4 py-2 text-muted-foreground">Nenhum.</li>}
      </ul>
    </Card>
  );
}

type SumRow = { codigo: string; rubrica: string; tipo: string; quantidade: number; valor: string };

function Summary({ run }: { run: PayrollRun }) {
  const { data, error } = useSWR<SumRow[]>(`folha/folhas/${run.id}/summary`, fetcher);
  if (error) return <ErrorState error={error} />;
  return (
    <Card>
      <div className="flex justify-end border-b px-4 py-2">
        <Button size="sm" variant="outline" disabled={!data}
          onClick={() => data && downloadCsv(`resumo-rubricas-${run.folha}-${run.month}-${run.year}.csv`, ["Código", "Rubrica", "Tipo", "Quantidade", "Valor"],
            data.map((r) => [r.codigo, r.rubrica, r.tipo, r.quantidade, br(r.valor)]))}><Download /> Planilha</Button>
      </div>
      <Table>
        <TableHeader><TableRow><TableHead>Código</TableHead><TableHead>Rubrica</TableHead><TableHead>Tipo</TableHead><TableHead className="text-right">Qtde.</TableHead><TableHead className="text-right">Valor</TableHead></TableRow></TableHeader>
        <TableBody>
          {!data && <LoadingRows cols={5} />}
          {data?.map((r) => (
            <TableRow key={r.codigo + r.tipo}>
              <TableCell className="font-mono text-xs">{r.codigo}</TableCell><TableCell>{r.rubrica}</TableCell>
              <TableCell><Badge variant={r.tipo === "PROVENTO" ? "success" : "neutral"}>{r.tipo.toLowerCase()}</Badge></TableCell>
              <TableCell className="text-right tabular">{formatInt(r.quantidade)}</TableCell>
              <TableCell className="text-right tabular">{formatCurrency(r.valor)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

type CreditRow = { banco: string; banco_nome: string; agencia: string; conta: string; tipo: string; cpf: string; nome: string; liquido: string };

function Credit({ run }: { run: PayrollRun }) {
  const { can } = useSession();
  const allowed = can("folha.arquivo_bancario", "exportar") || can("folha.relatorios", "exportar");
  const { data, error } = useSWR<CreditRow[]>(allowed ? `folha/folhas/${run.id}/credit` : null, fetcher);
  if (!allowed) return <Card className="p-4 text-xs text-muted-foreground">Sem permissão para a relação de crédito.</Card>;
  if (error) return <ErrorState error={error} />;
  const byBank = new Map<string, { nome: string; qtd: number; total: number }>();
  data?.forEach((r) => {
    const k = r.banco || "—";
    const cur = byBank.get(k) ?? { nome: r.banco_nome || "Sem conta bancária", qtd: 0, total: 0 };
    cur.qtd += 1;
    cur.total += Number(r.liquido);
    byBank.set(k, cur);
  });
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-xs">
        <span className="text-muted-foreground">Relação para crédito em conta. O arquivo do banco (CNAB 240) é gerado em Gestão Financeira › Pagamentos, a partir da folha fechada.</span>
        <Button size="sm" variant="outline" disabled={!data}
          onClick={() => data && downloadCsv(`credito-${run.folha}-${run.month}-${run.year}.csv`, ["Banco", "Agência", "Conta", "Tipo", "CPF", "Nome", "Líquido"],
            data.map((r) => [r.banco, r.agencia, r.conta, r.tipo, formatCPF(r.cpf), r.nome, br(r.liquido)]))}><Download /> Planilha</Button>
      </div>
      <div className="flex flex-wrap gap-2 border-b px-4 py-2">
        {[...byBank.entries()].map(([k, v]) => (
          <Badge key={k} variant={k === "—" ? "warning" : "neutral"}>{k} {v.nome}: {v.qtd} · {formatCurrency(v.total)}</Badge>
        ))}
      </div>
      <Table>
        <TableHeader><TableRow><TableHead>Banco</TableHead><TableHead>Agência</TableHead><TableHead>Conta</TableHead><TableHead>Beneficiário</TableHead><TableHead className="text-right">Líquido</TableHead></TableRow></TableHeader>
        <TableBody>
          {!data && <LoadingRows cols={5} />}
          {data?.map((r, i) => (
            <TableRow key={i}>
              <TableCell>{r.banco || <span className="text-warning">sem conta</span>}</TableCell><TableCell>{r.agencia}</TableCell><TableCell>{r.conta}</TableCell>
              <TableCell>{r.nome}</TableCell><TableCell className="text-right tabular">{formatCurrency(r.liquido)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
