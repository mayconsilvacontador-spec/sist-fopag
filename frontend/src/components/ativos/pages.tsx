"use client";

/** Folha de Ativos (servidores em atividade) — separada da folha de benefícios (aposentados e pensionistas). */
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { Calculator, CheckCircle2, Lock, Pencil, Plus, Printer, RotateCcw, Search, Trash2 } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const STATUS_VARIANT: Record<string, "neutral" | "info" | "warning" | "success"> = { ABERTA: "neutral", CALCULADA: "info", CONFERIDA: "warning", FECHADA: "success" };
const SEG: Record<string, string> = { FINANCEIRO: "Financeiro", PREVIDENCIARIO: "Previdenciário", COMPRA_VIDAS: "Compra de Vidas" };

type Run = {
  id: string; organ: string; organ_name: string; year: number; month: number; status: string; status_display: string;
  totals: Record<string, string | number | Record<string, Record<string, string | number>>>; warnings: string[];
  calculated_at: string | null; checked_by_name: string; checked_at: string | null; closed_by_name: string; closed_at: string | null;
};
type Slip = { id: string; person_name: string; person_cpf: string; registration: string; position_name: string; segment: string; days: number; gross: string; discounts: string; net: string; rpps_base: string; employer_contribution: string; warnings: string[] };
type SlipDetail = Slip & { ir_base: string; bank: Record<string, string>; memory: Record<string, Record<string, unknown>>; items: { code: string; name: string; kind: string; reference: string; amount: string }[]; run: Run };

// ============================================================ Folhas
export function ActiveRunsPage() {
  return <RequirePermission module="ativos.folha"><Runs /></RequirePermission>;
}

function Runs() {
  const { can } = useSession();
  const router = useRouter();
  const [organ, setOrgan] = useState("");
  const [page, setPage] = useState(1);
  const [opening, setOpening] = useState(false);
  const organs = useSWR<{ id: string; nome: string; servidores_ativos: number }[]>("ativos/folhas/orgaos", fetcher);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Run>>(`ativos/folhas${qs({ orgao: organ, page })}`, fetcher, { keepPreviousData: true });
  const now = new Date();
  return (
    <>
      <PageHeader title="Folha de Ativos" description="Folha dos servidores em atividade, uma por órgão e competência — separada da folha de aposentados e pensionistas."
        breadcrumb={[{ label: "Folha de Ativos" }, { label: "Folhas" }]}
        actions={can("ativos.folha", "incluir") && <Button onClick={() => setOpening(true)}><Plus /> Abrir folha</Button>} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <Select className="w-80" value={organ} onChange={(e) => { setOrgan(e.target.value); setPage(1); }} aria-label="Órgão">
            <option value="">Todos os órgãos</option>{organs.data?.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
          </Select>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Competência</TableHead><TableHead>Órgão</TableHead><TableHead className="text-right">Servidores</TableHead><TableHead className="text-right">Proventos</TableHead><TableHead className="text-right">Descontos</TableHead><TableHead className="text-right">Líquido</TableHead><TableHead className="text-right">Patronal RPPS</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={8} />}
            {data?.results.map((r) => (
              <TableRow key={r.id} className="cursor-pointer" onClick={() => router.push(`/ativos/folhas/${r.id}`)}>
                <TableCell className="font-medium text-primary">{MONTHS[r.month - 1]}/{r.year}</TableCell>
                <TableCell className="text-xs">{r.organ_name}</TableCell>
                <TableCell className="text-right tabular">{String(r.totals.servidores ?? "—")}</TableCell>
                <TableCell className="text-right tabular">{r.totals.proventos ? formatCurrency(String(r.totals.proventos)) : "—"}</TableCell>
                <TableCell className="text-right tabular">{r.totals.descontos ? formatCurrency(String(r.totals.descontos)) : "—"}</TableCell>
                <TableCell className="text-right tabular font-medium">{r.totals.liquido ? formatCurrency(String(r.totals.liquido)) : "—"}</TableCell>
                <TableCell className="text-right tabular">{r.totals.contribuicao_patronal ? formatCurrency(String(r.totals.contribuicao_patronal)) : "—"}</TableCell>
                <TableCell><Badge variant={STATUS_VARIANT[r.status]}>{r.status_display}</Badge></TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={8} text="Nenhuma folha de ativos. Clique em “Abrir folha”." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {opening && (
        <FormDialog title="Abrir folha de ativos" size="sm" description="Uma folha por órgão (empregador) e competência."
          initial={{ ano: now.getFullYear(), mes: now.getMonth() + 1 }}
          fields={[
            { name: "orgao", label: "Órgão", type: "select", required: true, wide: true, options: (organs.data ?? []).map((o) => ({ value: o.id, label: `${o.nome} (${o.servidores_ativos} ativos)` })) },
            { name: "mes", label: "Mês", type: "select", required: true, options: MONTHS.map((m, i) => ({ value: i + 1, label: m })) },
            { name: "ano", label: "Ano", type: "number", required: true },
          ]}
          submitLabel="Abrir" onClose={() => setOpening(false)}
          submit={async (body) => { const r = await api<Run>("ativos/folhas", { method: "POST", body }); toast.success("Folha aberta. Agora calcule."); mutate(); router.push(`/ativos/folhas/${r.id}`); }} />
      )}
    </>
  );
}

export function ActiveRunDetailPage({ id }: { id: string }) {
  return <RequirePermission module="ativos.folha"><RunDetail id={id} /></RequirePermission>;
}

function RunDetail({ id }: { id: string }) {
  const { can } = useSession();
  const router = useRouter();
  const { data: run, error, mutate } = useSWR<Run>(`ativos/folhas/${id}`, fetcher);
  const [term, setTerm] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [slip, setSlip] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"reabrir" | "excluir" | null>(null);
  useEffect(() => { const t = setTimeout(() => { setSearch(term); setPage(1); }, 300); return () => clearTimeout(t); }, [term]);
  const slips = useSWR<Paginated<Slip>>(run && run.status !== "ABERTA" ? `ativos/folhas/${id}/contracheques${qs({ search, page })}` : null, fetcher, { keepPreviousData: true });
  const act = async (path: string, ok: string) => {
    setBusy(true);
    try { await api(`ativos/folhas/${id}/${path}`, { method: "POST", body: {} }); toast.success(ok); mutate(); slips.mutate(); }
    catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  if (error) return <ErrorState error={error} />;
  if (!run) return null;
  const t = run.totals;
  const money = (k: string) => (t[k] ? formatCurrency(String(t[k])) : "—");
  const porMassa = (t.por_massa ?? {}) as Record<string, Record<string, string | number>>;
  return (
    <>
      <PageHeader title={`Folha de Ativos ${MONTHS[run.month - 1]}/${run.year}`} description={run.organ_name}
        breadcrumb={[{ label: "Folha de Ativos" }, { label: "Folhas", href: "/ativos/folhas" }, { label: `${run.month}/${run.year}` }]}
        actions={<div className="flex flex-wrap gap-2">
          {["ABERTA", "CALCULADA", "CONFERIDA"].includes(run.status) && can("ativos.folha", "calcular") && <Button onClick={() => act("calcular", "Folha calculada.")} disabled={busy}><Calculator /> {run.status === "ABERTA" ? "Calcular" : "Recalcular"}</Button>}
          {run.status === "CALCULADA" && can("ativos.folha", "aprovar") && <Button variant="outline" onClick={() => act("conferir", "Folha conferida.")} disabled={busy}><CheckCircle2 /> Conferir</Button>}
          {run.status === "CONFERIDA" && can("ativos.folha", "fechar") && <Button variant="outline" onClick={() => act("fechar", "Folha fechada.")} disabled={busy}><Lock /> Fechar</Button>}
          {run.status === "FECHADA" && can("ativos.folha", "reabrir") && <Button variant="ghost" onClick={() => setDialog("reabrir")}><RotateCcw /> Reabrir</Button>}
          {run.status !== "FECHADA" && can("ativos.folha", "excluir") && <Button variant="ghost" onClick={() => setDialog("excluir")}><Trash2 className="text-destructive" /> Excluir</Button>}
        </div>} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[["Servidores", String(t.servidores ?? "—")], ["Proventos", money("proventos")], ["Descontos", money("descontos")], ["Líquido", money("liquido")],
          ["Contribuição dos servidores (RPPS)", money("contribuicao_servidor")], ["Contribuição patronal (RPPS)", money("contribuicao_patronal")],
          ["IRRF retido", money("irrf")], ["Sem conta bancária", String(t.sem_conta ?? "—")]].map(([l, v]) => (
          <Card key={l}><CardContent className="p-3"><div className="text-2xs uppercase text-muted-foreground">{l}</div><div className="text-lg font-semibold tabular">{v}</div></CardContent></Card>
        ))}
      </div>
      <div className="mb-3 flex flex-wrap gap-3 text-xs">
        <Badge variant={STATUS_VARIANT[run.status]}>{run.status_display}</Badge>
        {run.calculated_at && <span className="text-muted-foreground">Calculada em {formatDateTime(run.calculated_at)}</span>}
        {run.checked_at && <span className="text-muted-foreground">· conferida por {run.checked_by_name}</span>}
        {run.closed_at && <span className="text-muted-foreground">· fechada por {run.closed_by_name} em {formatDateTime(run.closed_at)}</span>}
        {Object.entries(porMassa).map(([seg, v]) => <span key={seg} className="rounded border px-2 py-0.5">{SEG[seg] ?? seg}: {String(v.servidores)} serv. · base {formatCurrency(String(v.base_rpps))} · servidor {formatCurrency(String(v.servidor))} · patronal {formatCurrency(String(v.patronal))}</span>)}
      </div>
      {run.warnings.length > 0 && <Card className="mb-3 border-warning-border bg-warning-soft"><CardContent className="space-y-0.5 p-3 text-xs">{run.warnings.map((w, i) => <div key={i}>• {w}</div>)}</CardContent></Card>}
      {run.status === "ABERTA" ? (
        <Card><CardContent className="p-6 text-sm text-muted-foreground">Folha aberta. Confira a <Link className="text-primary underline" href="/ativos/vencimentos">tabela de vencimentos</Link>, as <Link className="text-primary underline" href="/ativos/rubricas">rubricas</Link> e os <Link className="text-primary underline" href="/ativos/lancamentos">lançamentos</Link> e clique em <b>Calcular</b>.</CardContent></Card>
      ) : (
        <Card>
          <div className="flex items-center gap-3 border-b px-4 py-2.5">
            <div className="relative w-72"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-8" placeholder="Nome, CPF ou matrícula" value={term} onChange={(e) => setTerm(e.target.value)} /></div>
          </div>
          <Table>
            <TableHeader><TableRow><TableHead>Servidor</TableHead><TableHead>Cargo</TableHead><TableHead>Massa</TableHead><TableHead className="text-right">Dias</TableHead><TableHead className="text-right">Proventos</TableHead><TableHead className="text-right">Descontos</TableHead><TableHead className="text-right">Líquido</TableHead></TableRow></TableHeader>
            <TableBody>
              {slips.isLoading && !slips.data && <LoadingRows cols={7} />}
              {slips.data?.results.map((s) => (
                <TableRow key={s.id} className="cursor-pointer" onClick={() => setSlip(s.id)}>
                  <TableCell><div className="font-medium text-primary">{s.person_name}</div><div className="text-2xs text-muted-foreground">Matrícula {s.registration} · CPF {s.person_cpf}</div>
                    {s.warnings.length > 0 && <div className="text-2xs text-warning">{s.warnings.join(" · ")}</div>}</TableCell>
                  <TableCell className="text-xs">{s.position_name}</TableCell>
                  <TableCell className="text-xs">{SEG[s.segment] ?? s.segment}</TableCell>
                  <TableCell className="text-right tabular">{s.days}</TableCell>
                  <TableCell className="text-right tabular">{formatCurrency(s.gross)}</TableCell>
                  <TableCell className="text-right tabular">{formatCurrency(s.discounts)}</TableCell>
                  <TableCell className={cn("text-right tabular font-medium", Number(s.net) < 0 && "text-critical")}>{formatCurrency(s.net)}</TableCell>
                </TableRow>
              ))}
              {slips.data?.results.length === 0 && <EmptyRow cols={7} text="Nenhum contracheque." />}
            </TableBody>
          </Table>
          {slips.data && <Pagination page={slips.data.page} numPages={slips.data.num_pages} count={slips.data.count} onChange={setPage} />}
        </Card>
      )}
      {slip && <PayslipDialog run={id} id={slip} onClose={() => setSlip(null)} />}
      {dialog && (
        <FormDialog title={dialog === "reabrir" ? "Reabrir folha" : "Excluir folha"} size="sm"
          description={dialog === "reabrir" ? "A folha volta para conferência; as parcelas baixadas no fechamento voltam a ficar em aberto." : "Use só para folha aberta por engano. Fica registrado na auditoria."}
          fields={[{ name: "justification", label: "Justificativa", type: "textarea", required: true, wide: true }]}
          submitLabel={dialog === "reabrir" ? "Reabrir" : "Excluir folha"} onClose={() => setDialog(null)}
          submit={async (body) => {
            await api(`ativos/folhas/${id}/${dialog}`, { method: "POST", body });
            toast.success(dialog === "reabrir" ? "Folha reaberta." : "Folha excluída.");
            if (dialog === "excluir") router.push("/ativos/folhas"); else mutate();
          }} />
      )}
    </>
  );
}

function PayslipDialog({ run, id, onClose }: { run: string; id: string; onClose: () => void }) {
  const { data } = useSWR<SlipDetail>(`ativos/folhas/${run}/contracheques/${id}`, fetcher);
  const prov = data?.items.filter((i) => i.kind === "PROVENTO") ?? [];
  const desc = data?.items.filter((i) => i.kind === "DESCONTO") ?? [];
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader><DialogTitle>Contracheque {data ? `— ${MONTHS[data.run.month - 1]}/${data.run.year}` : ""}</DialogTitle></DialogHeader>
        <DialogBody className="space-y-3 text-xs print:text-[11px]" id="contracheque">
          {data && <>
            <div className="grid gap-x-6 gap-y-1 rounded border p-3 sm:grid-cols-2">
              <div><span className="text-muted-foreground">Órgão: </span><b>{data.run.organ_name}</b></div>
              <div><span className="text-muted-foreground">Competência: </span>{MONTHS[data.run.month - 1]}/{data.run.year}</div>
              <div><span className="text-muted-foreground">Servidor: </span><b>{data.person_name}</b></div>
              <div><span className="text-muted-foreground">CPF: </span>{data.person_cpf} · <span className="text-muted-foreground">Matrícula: </span>{data.registration}</div>
              <div><span className="text-muted-foreground">Cargo: </span>{data.position_name}</div>
              <div><span className="text-muted-foreground">Dias trabalhados: </span>{data.days}</div>
              {data.bank?.banco && <div className="sm:col-span-2"><span className="text-muted-foreground">Crédito: </span>Banco {data.bank.banco} · Ag. {data.bank.agencia} · Conta {data.bank.conta}{data.bank.conta_dv ? `-${data.bank.conta_dv}` : ""}</div>}
            </div>
            <Table>
              <TableHeader><TableRow><TableHead>Código</TableHead><TableHead>Descrição</TableHead><TableHead>Ref.</TableHead><TableHead className="text-right">Proventos</TableHead><TableHead className="text-right">Descontos</TableHead></TableRow></TableHeader>
              <TableBody>
                {[...prov, ...desc].map((i, k) => (
                  <TableRow key={k}><TableCell>{i.code}</TableCell><TableCell>{i.name}</TableCell><TableCell>{i.reference}</TableCell>
                    <TableCell className="text-right tabular">{i.kind === "PROVENTO" ? formatCurrency(i.amount) : ""}</TableCell>
                    <TableCell className="text-right tabular">{i.kind === "DESCONTO" ? formatCurrency(i.amount) : ""}</TableCell></TableRow>))}
                <TableRow><TableCell colSpan={3} className="font-semibold">Totais</TableCell><TableCell className="text-right font-semibold tabular">{formatCurrency(data.gross)}</TableCell><TableCell className="text-right font-semibold tabular">{formatCurrency(data.discounts)}</TableCell></TableRow>
                <TableRow><TableCell colSpan={3} className="font-semibold">Líquido</TableCell><TableCell colSpan={2} className="text-right text-base font-bold tabular">{formatCurrency(data.net)}</TableCell></TableRow>
              </TableBody>
            </Table>
            <div className="grid gap-2 text-2xs text-muted-foreground sm:grid-cols-4">
              <div>Base RPPS: <b>{formatCurrency(data.rpps_base)}</b></div><div>Base IRRF: <b>{formatCurrency(data.ir_base)}</b></div>
              <div>Patronal: <b>{formatCurrency(data.employer_contribution)}</b></div><div>Vencimento: {String(data.memory?.vencimento?.origem ?? "")}</div>
            </div>
            <Button size="sm" variant="outline" className="print:hidden" onClick={() => window.print()}><Printer /> Imprimir</Button>
          </>}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================ Tabela de vencimentos
type Scale = { id: string; position: string; position_name: string; level: string; amount: string; valid_from: string; valid_to: string | null; legal_basis: string };

export function SalaryScalePage() {
  return <RequirePermission module="ativos.vencimentos"><Scales /></RequirePermission>;
}

function Scales() {
  const { can } = useSession();
  const [all, setAll] = useState(false);
  const [term, setTerm] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Partial<Scale> | null>(null);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Scale>>(`ativos/vencimentos${qs({ vigentes: all ? undefined : 1, search: term, page })}`, fetcher, { keepPreviousData: true });
  const positions = useSWR<Paginated<{ id: string; name: string }>>("positions?page_size=500", fetcher);
  return (
    <>
      <PageHeader title="Tabela de Vencimentos" description="Valor de cada cargo (e nível/referência). Reajuste = novo valor com nova vigência; o valor anterior fica guardado."
        breadcrumb={[{ label: "Folha de Ativos" }, { label: "Tabela de Vencimentos" }]}
        actions={can("ativos.vencimentos", "incluir") && <Button onClick={() => setEditing({})}><Plus /> Novo valor / reajuste</Button>} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5 text-xs">
          <Input className="w-64" placeholder="Buscar cargo" value={term} onChange={(e) => { setTerm(e.target.value); setPage(1); }} />
          <label className="flex items-center gap-2"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Mostrar histórico (valores antigos)</label>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Cargo</TableHead><TableHead>Nível</TableHead><TableHead className="text-right">Vencimento</TableHead><TableHead>Vigência</TableHead><TableHead>Lei / ato</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={6} />}
            {data?.results.map((s) => (
              <TableRow key={s.id} className={cn(s.valid_to && "text-muted-foreground")}>
                <TableCell className="font-medium">{s.position_name}</TableCell><TableCell>{s.level || "todos"}</TableCell>
                <TableCell className="text-right tabular">{formatCurrency(s.amount)}</TableCell>
                <TableCell className="text-xs">desde {formatDate(s.valid_from)}{s.valid_to ? ` até ${formatDate(s.valid_to)}` : ""}</TableCell>
                <TableCell className="text-xs">{s.legal_basis}</TableCell>
                <TableCell>{!s.valid_to && can("ativos.vencimentos", "incluir") && <Button size="icon" variant="ghost" title="Reajustar" onClick={() => setEditing({ position: s.position, level: s.level })}><Pencil /></Button>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum valor cadastrado. Sem tabela, o sistema usa o “vencimento base” do vínculo." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {editing && (
        <FormDialog title="Novo valor / reajuste" size="md" description="Se já houver valor para o mesmo cargo e nível, ele é encerrado na véspera da nova vigência."
          initial={{ position: editing.position ?? "", level: editing.level ?? "" }}
          fields={[
            { name: "position", label: "Cargo", type: "select", required: true, wide: true, options: (positions.data?.results ?? []).map((p) => ({ value: p.id, label: p.name })) },
            { name: "level", label: "Nível / referência (vazio = todos)", hint: "Igual ao campo “classe / nível” do vínculo" },
            { name: "amount", label: "Vencimento (R$)", type: "money", required: true },
            { name: "valid_from", label: "A partir de", type: "date", required: true },
            { name: "legal_basis", label: "Lei / ato do reajuste", wide: true },
          ] as FieldDef[]}
          submitLabel="Salvar" onClose={() => setEditing(null)}
          submit={async (body) => { await api("ativos/vencimentos", { method: "POST", body }); toast.success("Vencimento registrado."); mutate(); }} />
      )}
    </>
  );
}

// ============================================================ Rubricas
type Rubric = { id: string; code: string; name: string; kind: string; kind_display: string; calc: string; calc_display: string; inc_rpps: boolean; inc_ir: boolean; percent: string | null; period_years: number | null; max_percent: string | null; legal_basis: string; active: boolean };
const CALCS = [["VENCIMENTO", "Vencimento (tabela)"], ["ADICIONAL_TEMPO", "Adicional por tempo de serviço"], ["LANCAMENTO", "Lançamento (valor ou %)"], ["FALTAS", "Faltas (histórico funcional)"], ["CONTRIB_RPPS", "Contribuição ao RPPS"], ["IRRF", "IRRF"]];

export function ActiveRubricsPage() {
  return <RequirePermission module="ativos.rubricas"><Rubrics /></RequirePermission>;
}

function Rubrics() {
  const { can } = useSession();
  const { data, error, mutate } = useSWR<Rubric[]>("ativos/rubricas", fetcher);
  const [editing, setEditing] = useState<Rubric | "new" | null>(null);
  const r = editing && editing !== "new" ? editing : null;
  return (
    <>
      <PageHeader title="Rubricas da Folha de Ativos" description="Proventos e descontos dos servidores ativos. A sugestão inicial deve ser conferida com o estatuto de cada órgão (ex.: regra do adicional por tempo)."
        breadcrumb={[{ label: "Folha de Ativos" }, { label: "Rubricas" }]}
        actions={can("ativos.rubricas", "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Nova rubrica</Button>} />
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Código</TableHead><TableHead>Nome</TableHead><TableHead>Tipo</TableHead><TableHead>Cálculo</TableHead><TableHead>RPPS</TableHead><TableHead>IR</TableHead><TableHead>Situação</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
          <TableBody>
            {data?.map((x) => (
              <TableRow key={x.id} className={cn(!x.active && "text-muted-foreground")}>
                <TableCell className="font-mono">{x.code}</TableCell><TableCell className="font-medium">{x.name}</TableCell>
                <TableCell><Badge variant={x.kind === "PROVENTO" ? "success" : "warning"}>{x.kind_display.split(" ")[0]}</Badge></TableCell>
                <TableCell className="text-xs">{x.calc_display}{x.calc === "ADICIONAL_TEMPO" && x.percent ? ` — ${x.percent}% a cada ${x.period_years} anos (máx. ${x.max_percent ?? "—"}%)` : ""}</TableCell>
                <TableCell>{x.inc_rpps ? "Sim" : "—"}</TableCell><TableCell>{x.inc_ir ? "Sim" : "—"}</TableCell>
                <TableCell>{x.active ? "Ativa" : "Inativa"}</TableCell>
                <TableCell>{can("ativos.rubricas", "editar") && <Button size="icon" variant="ghost" onClick={() => setEditing(x)}><Pencil /></Button>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      {editing && (
        <FormDialog title={r ? `Rubrica ${r.code}` : "Nova rubrica"} size="md"
          initial={r ? { ...r } : { kind: "PROVENTO", calc: "LANCAMENTO", inc_rpps: true, inc_ir: true, active: true }}
          fields={[
            { name: "code", label: "Código", required: true }, { name: "name", label: "Nome", required: true },
            { name: "kind", label: "Tipo", type: "select", required: true, options: [{ value: "PROVENTO", label: "Provento" }, { value: "DESCONTO", label: "Desconto" }] },
            { name: "calc", label: "Forma de cálculo", type: "select", required: true, options: CALCS.map(([v, l]) => ({ value: v, label: l })) },
            { name: "percent", label: "Adicional: % por período", type: "number" }, { name: "period_years", label: "Adicional: a cada (anos)", type: "number" },
            { name: "max_percent", label: "Adicional: limite (%)", type: "number" }, { name: "legal_basis", label: "Fundamentação" },
            { name: "inc_rpps", label: "Incide contribuição ao RPPS", type: "checkbox" }, { name: "inc_ir", label: "Incide IRRF", type: "checkbox" },
            { name: "active", label: "Ativa", type: "checkbox" },
          ] as FieldDef[]}
          submitLabel="Salvar" onClose={() => setEditing(null)}
          submit={async (body) => {
            if (r) await api(`ativos/rubricas/${r.id}`, { method: "PATCH", body }); else await api("ativos/rubricas", { method: "POST", body });
            toast.success("Rubrica salva."); mutate();
          }} />
      )}
    </>
  );
}

// ============================================================ Lançamentos
type Entry = { id: string; link: string; person_name: string; registration: string; organ_name: string; rubric: string; rubric_label: string; rubric_kind: string; amount: string | null; percent: string | null; start: string; end: string | null; installments: number | null; paid_installments: number; reference: string; active: boolean };
type LinkRow = { id: string; person_name: string; registration: string; organ_name: string; position_name: string };

export function ActiveEntriesPage() {
  return <RequirePermission module="ativos.lancamentos"><Entries /></RequirePermission>;
}

function Entries() {
  const { can } = useSession();
  const sp = useSearchParams();
  const [term, setTerm] = useState(sp.get("q") ?? "");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Entry | "new" | null>(null);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Entry>>(`ativos/lancamentos${qs({ search: term, page })}`, fetcher, { keepPreviousData: true });
  return (
    <>
      <PageHeader title="Lançamentos da Folha de Ativos" description="Gratificações, funções, horas extras, consignações e outros valores de cada servidor (fixos, por período ou parcelados)."
        breadcrumb={[{ label: "Folha de Ativos" }, { label: "Lançamentos" }]}
        actions={can("ativos.lancamentos", "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Novo lançamento</Button>} />
      <Card>
        <div className="border-b px-4 py-2.5"><Input className="w-72" placeholder="Nome, CPF, matrícula ou código da rubrica" value={term} onChange={(e) => { setTerm(e.target.value); setPage(1); }} /></div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Servidor</TableHead><TableHead>Rubrica</TableHead><TableHead className="text-right">Valor</TableHead><TableHead>Período</TableHead><TableHead>Parcelas</TableHead><TableHead>Situação</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={7} />}
            {data?.results.map((e) => (
              <TableRow key={e.id} className={cn(!e.active && "text-muted-foreground")}>
                <TableCell><div className="font-medium">{e.person_name}</div><div className="text-2xs text-muted-foreground">Mat. {e.registration} · {e.organ_name}</div></TableCell>
                <TableCell className="text-xs">{e.rubric_label}</TableCell>
                <TableCell className="text-right tabular">{e.amount ? formatCurrency(e.amount) : `${e.percent}% do venc.`}</TableCell>
                <TableCell className="text-xs">{e.start.slice(5, 7)}/{e.start.slice(0, 4)}{e.end ? ` a ${e.end.slice(5, 7)}/${e.end.slice(0, 4)}` : " em diante"}</TableCell>
                <TableCell className="text-xs">{e.installments ? `${e.paid_installments}/${e.installments}` : "—"}</TableCell>
                <TableCell>{e.active ? "Ativo" : "Inativo"}</TableCell>
                <TableCell>{can("ativos.lancamentos", "editar") && <Button size="icon" variant="ghost" onClick={() => setEditing(e)}><Pencil /></Button>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={7} text="Nenhum lançamento." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {editing && <EntryDialog entry={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => mutate()} />}
    </>
  );
}

function EntryDialog({ entry, onClose, onSaved }: { entry: Entry | null; onClose: () => void; onSaved: () => void }) {
  const rubrics = useSWR<Rubric[]>("ativos/rubricas?lancamento=1", fetcher);
  const [term, setTerm] = useState("");
  const [link, setLink] = useState<LinkRow | null>(null);
  const links = useSWR<Paginated<LinkRow>>(!entry && term.length >= 3 ? `employment-links${qs({ search: term, status: "ATIVO", page_size: 8 })}` : null, fetcher);
  const [f, setF] = useState({ rubric: entry?.rubric ?? "", amount: entry?.amount?.replace(".", ",") ?? "", percent: entry?.percent ?? "",
    start: entry?.start?.slice(0, 7) ?? new Date().toISOString().slice(0, 7), end: entry?.end?.slice(0, 7) ?? "", installments: String(entry?.installments ?? ""),
    reference: entry?.reference ?? "", active: entry?.active ?? true });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const body = { link: entry?.link ?? link?.id, rubric: f.rubric, amount: f.amount ? f.amount.replace(/\./g, "").replace(",", ".") : null,
        percent: f.percent || null, start: `${f.start}-01`, end: f.end ? `${f.end}-01` : null, installments: f.installments || null, reference: f.reference, active: f.active };
      if (entry) await api(`ativos/lancamentos/${entry.id}`, { method: "PATCH", body }); else await api("ativos/lancamentos", { method: "POST", body });
      toast.success("Lançamento salvo."); onSaved(); onClose();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="md">
        <DialogHeader><DialogTitle>{entry ? "Editar lançamento" : "Novo lançamento"}</DialogTitle></DialogHeader>
        <DialogBody className="grid gap-3 text-xs sm:grid-cols-2">
          <FormField label="Servidor (vínculo)" required className="sm:col-span-2">
            {entry ? <div className="text-sm font-medium">{entry.person_name} — mat. {entry.registration}</div> : link
              ? <div className="flex items-center justify-between rounded border bg-muted/40 px-3 py-2"><span><b>{link.person_name}</b> · mat. {link.registration} · {link.organ_name}</span><Button size="sm" variant="ghost" onClick={() => setLink(null)}>Trocar</Button></div>
              : <div className="relative"><Input autoFocus placeholder="Nome, CPF ou matrícula (mín. 3 caracteres)" value={term} onChange={(e) => setTerm(e.target.value)} />
                {links.data && <ul className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded border bg-popover shadow">{links.data.results.map((l) => (
                  <li key={l.id}><button type="button" className="w-full px-3 py-1.5 text-left hover:bg-muted" onClick={() => setLink(l)}>{l.person_name} · mat. {l.registration} · {l.organ_name} · {l.position_name}</button></li>))}
                  {links.data.results.length === 0 && <li className="px-3 py-2 text-muted-foreground">Nenhum vínculo ativo encontrado.</li>}</ul>}</div>}
          </FormField>
          <FormField label="Rubrica" required className="sm:col-span-2">
            <Select value={f.rubric} onChange={(e) => setF({ ...f, rubric: e.target.value })}><option value="" disabled>Selecione…</option>
              {rubrics.data?.map((r) => <option key={r.id} value={r.id}>{r.code} — {r.name} ({r.kind === "PROVENTO" ? "provento" : "desconto"})</option>)}</Select>
          </FormField>
          <FormField label="Valor (R$)" hint="Ou use o % do vencimento"><Input inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value, percent: "" })} /></FormField>
          <FormField label="% do vencimento"><Input inputMode="decimal" value={f.percent} onChange={(e) => setF({ ...f, percent: e.target.value, amount: "" })} /></FormField>
          <FormField label="A partir da competência" required><Input type="month" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></FormField>
          <FormField label="Até a competência (opcional)"><Input type="month" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></FormField>
          <FormField label="Nº de parcelas (opcional)"><Input type="number" value={f.installments} onChange={(e) => setF({ ...f, installments: e.target.value })} /></FormField>
          <FormField label="Referência / contrato"><Input value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></FormField>
          {entry && <label className="flex items-center gap-2"><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Ativo</label>}
        </DialogBody>
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} disabled={busy || !f.rubric || (!entry && !link)}>Salvar</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
