"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Calculator, Download, Plus, Receipt, Undo2 } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { downloadCsv } from "@/components/folha/run-detail";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import type { PayrollRun } from "@/lib/types";

import { PayDialog, SituationBadge, compLabel, useAccounts, usePlans } from "./common";

const crumbs = (t: string) => [{ label: "Arrecadação" }, { label: t }];
const br = (v: string) => v.replace(".", ",");

// ------------------------------------------------------------------ Contribuições
type Contribution = {
  id: string; plan: string; plan_code: string; organ: string | null; organ_name: string; kind: string; kind_display: string;
  competence: string; base: string; rate: string; amount: string; due_date: string; source: string; source_display: string;
  paid: string; situation: string; notes: string;
};

export function ContributionsPage({ kind }: { kind: "SERVIDOR" | "PATRONAL" }) {
  return <RequirePermission module={kind === "PATRONAL" ? "arrecadacao.patronal" : "arrecadacao.servidor"}><Contributions kind={kind} /></RequirePermission>;
}

function Contributions({ kind }: { kind: "SERVIDOR" | "PATRONAL" }) {
  const { can } = useSession();
  const moduleCode = kind === "PATRONAL" ? "arrecadacao.patronal" : "arrecadacao.servidor";
  const [comp, setComp] = useState(new Date().toISOString().slice(0, 7));
  const [showRetired, setShowRetired] = useState(false);
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<"estimate" | "payroll" | null>(null);
  const [editing, setEditing] = useState<Contribution | null>(null);
  const [paying, setPaying] = useState<Contribution | null>(null);
  const listKind = kind === "SERVIDOR" && showRetired ? "APOSENTADOS" : kind;
  const { data, error, isLoading, mutate } = useSWR<Paginated<Contribution>>(
    `arrecadacao/contribuicoes${qs({ kind: listKind, competence: comp ? `${comp}-01` : undefined, page })}`, fetcher);
  const runs = useSWR<Paginated<PayrollRun>>(dialog === "payroll" ? "folha/folhas?situacoes=FECHADA,PAGA&page_size=50" : null, fetcher);
  const title = kind === "PATRONAL" ? "Contribuição Patronal" : "Contribuição do Servidor";
  return (
    <>
      <PageHeader title={title} breadcrumb={crumbs(title)}
        description={kind === "PATRONAL"
          ? "Contribuição do ente (24% a partir de 09/2025 — parâmetro arrecadacao.aliquota_patronal) por órgão, plano e competência."
          : "Contribuição dos servidores ativos (14%) por órgão e plano, e a contribuição retida de aposentados e pensionistas na folha do RPPS."}
        actions={can(moduleCode, "incluir") && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setDialog("estimate")}><Calculator /> Calcular competência</Button>
            {kind === "SERVIDOR" && <Button variant="outline" onClick={() => setDialog("payroll")}><Receipt /> Registrar retenções da folha</Button>}
          </div>
        )} />
      <Card className="mb-3 border-info/30 bg-info/5 px-4 py-2 text-xs">
        O cálculo usa o <b>vencimento base</b> dos vínculos ativos (estimativa). Quando o órgão enviar a remuneração de contribuição, edite a base — a origem passa a “Informada pelo órgão”.
      </Card>
      {error && <ErrorState error={error} />}
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <Input type="month" className="w-44" value={comp} onChange={(e) => { setComp(e.target.value); setPage(1); }} aria-label="Competência" />
          {kind === "SERVIDOR" && (
            <Select className="w-64" value={showRetired ? "1" : "0"} onChange={(e) => { setShowRetired(e.target.value === "1"); setPage(1); }} aria-label="Tipo">
              <option value="0">Servidores ativos</option><option value="1">Aposentados e pensionistas (folha do RPPS)</option>
            </Select>
          )}
        </div>
        <Table>
          <TableHeader><TableRow><TableHead>Órgão</TableHead><TableHead>Plano</TableHead><TableHead className="text-right">Base</TableHead><TableHead className="text-right">Devido</TableHead><TableHead className="text-right">Pago</TableHead><TableHead>Vencimento</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={8} />}
            {data?.results.map((c) => (
              <TableRow key={c.id}>
                <TableCell><div className="font-medium">{c.organ_name}</div><div className="text-2xs text-muted-foreground">{c.source_display}{Number(c.rate) ? ` · ${(Number(c.rate) * 100).toLocaleString("pt-BR")}%` : ""}</div></TableCell>
                <TableCell><Badge variant="info">{c.plan_code}</Badge></TableCell>
                <TableCell className="text-right tabular">{formatCurrency(c.base)}</TableCell>
                <TableCell className="text-right tabular">{formatCurrency(c.amount)}</TableCell>
                <TableCell className="text-right tabular">{formatCurrency(c.paid)}</TableCell>
                <TableCell>{formatDate(c.due_date)}</TableCell>
                <TableCell><SituationBadge s={c.situation} /></TableCell>
                <TableCell className="whitespace-nowrap">
                  {can(moduleCode, "editar") && c.source !== "FOLHA" && <Button size="sm" variant="ghost" onClick={() => setEditing(c)}>Editar</Button>}
                  {can(moduleCode, "editar") && c.situation !== "PAGO" && <Button size="sm" variant="outline" onClick={() => setPaying(c)}>Baixar</Button>}
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={8} text="Nenhuma contribuição na competência. Use “Calcular competência”." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {dialog === "estimate" && (
        <FormDialog title="Calcular contribuições da competência" size="sm" onClose={() => setDialog(null)}
          description="Cria as contribuições do servidor E patronal de cada órgão e plano (as já existentes não são recriadas)."
          fields={[{ name: "competence", label: "Competência", required: true, wide: true }]} initial={{ competence: comp }}
          submitLabel="Calcular"
          submit={async (body) => {
            const r = await api<{ criadas: number; vinculos_sem_vencimento: number }>(`arrecadacao/contribuicoes/estimate?kind=${kind}`, { method: "POST", body });
            toast.success(`${r.criadas} contribuição(ões) criada(s).${r.vinculos_sem_vencimento ? ` ${r.vinculos_sem_vencimento} vínculo(s) sem vencimento base foram ignorados.` : ""}`);
            if (typeof body.competence === "string") setComp(body.competence.slice(0, 7));
            mutate();
          }} />
      )}
      {dialog === "payroll" && (
        <FormDialog title="Registrar retenções da folha de benefícios" size="sm" onClose={() => setDialog(null)}
          description="A contribuição descontada de aposentados e pensionistas vira contribuição e receita do plano da folha."
          fields={[{ name: "run", label: "Folha fechada/paga", type: "select", required: true, wide: true,
            options: (runs.data?.results ?? []).map((r) => ({ value: r.id, label: `${String(r.month).padStart(2, "0")}/${r.year} — ${r.folha}${r.kind === "DECIMO" ? " (13º)" : ""}` })) }]}
          submitLabel="Registrar"
          submit={async (body) => {
            await api("arrecadacao/contribuicoes/from-payroll?kind=APOSENTADOS", { method: "POST", body });
            toast.success("Retenção registrada como contribuição e receita.");
            setShowRetired(true);
            mutate();
          }} />
      )}
      {editing && (
        <FormDialog title={`Editar — ${editing.organ_name}`} size="sm" onClose={() => setEditing(null)}
          description="O valor devido é recalculado (base × alíquota)."
          initial={{ base: editing.base.replace(".", ","), rate: editing.rate, due_date: editing.due_date, notes: editing.notes, source: "INFORMADA" }}
          fields={[
            { name: "base", label: "Base de cálculo (R$)", type: "money", required: true },
            { name: "rate", label: "Alíquota (ex.: 0.14)", required: true },
            { name: "due_date", label: "Vencimento", type: "date", required: true },
            { name: "source", label: "Origem", type: "select", required: true, options: [{ value: "INFORMADA", label: "Informada pelo órgão" }, { value: "ESTIMADA", label: "Estimada pelos vínculos" }] },
            { name: "notes", label: "Observações", type: "textarea" },
          ]}
          submit={async (body) => {
            await api(`arrecadacao/contribuicoes/${editing.id}?kind=${editing.kind}`, { method: "PATCH", body });
            toast.success("Contribuição atualizada.");
            mutate();
          }} />
      )}
      {paying && (
        <PayDialog title={`Baixa — ${paying.kind_display} · ${paying.organ_name} · ${compLabel(paying.competence)}`}
          path={`arrecadacao/contribuicoes/${paying.id}/pay?kind=${paying.kind}`} planId={paying.plan}
          suggested={(Number(paying.amount) - Number(paying.paid)).toFixed(2)} onClose={() => setPaying(null)} onDone={() => mutate()} />
      )}
    </>
  );
}

// ------------------------------------------------------------------ Aportes
type AporteRow = { id: string; plan: string; plan_code: string; kind: string; kind_display: string; competence: string; amount: string; due_date: string; legal_basis: string; paid: string; situation: string };
type Insuf = { plano: string; competencia: string; despesa_folha: string; receitas: string; insuficiencia: string; folhas_consideradas: number };

export function AportesPage() {
  return <RequirePermission module="arrecadacao.aportes"><Aportes /></RequirePermission>;
}

function Aportes() {
  const { can } = useSession();
  const plans = usePlans();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState<Record<string, unknown> | null>(null);
  const [paying, setPaying] = useState<AporteRow | null>(null);
  const [insComp, setInsComp] = useState(new Date().toISOString().slice(0, 7));
  const { data, error, mutate } = useSWR<Paginated<AporteRow>>(`arrecadacao/aportes${qs({ page })}`, fetcher);
  const ins = useSWR<Insuf>(insComp.length === 7 ? `arrecadacao/aportes/insufficiency?competence=${insComp}` : null, fetcher, { shouldRetryOnError: false });
  return (
    <>
      <PageHeader title="Aportes" breadcrumb={crumbs("Aportes")}
        description="Aportes do ente: equacionamento do déficit atuarial (Plano Previdenciário), cobertura de insuficiência financeira (Plano Financeiro) e Compra de Vidas."
        actions={can("arrecadacao.aportes", "incluir") && <Button onClick={() => setCreating({ kind: "DEFICIT", competence: `${insComp}-01` })}><Plus /> Novo aporte</Button>} />
      <Card className="mb-3 flex flex-wrap items-end gap-4 px-4 py-3 text-xs">
        <FormField label="Insuficiência financeira — competência" htmlFor="ins-comp" className="w-56"><Input id="ins-comp" type="month" value={insComp} onChange={(e) => setInsComp(e.target.value)} /></FormField>
        {ins.data && <>
          <div>Despesa da folha ({ins.data.plano}): <b>{formatCurrency(ins.data.despesa_folha)}</b></div>
          <div>Receitas do plano: <b>{formatCurrency(ins.data.receitas)}</b></div>
          <div>Insuficiência: <b className="text-critical">{formatCurrency(ins.data.insuficiencia)}</b> <span className="text-muted-foreground">({ins.data.folhas_consideradas} folha(s) fechada(s))</span></div>
          {can("arrecadacao.aportes", "incluir") && Number(ins.data.insuficiencia) > 0 && (
            <Button size="sm" variant="outline" onClick={() => setCreating({ kind: "INSUFICIENCIA", competence: `${insComp}-01`, amount: ins.data!.insuficiencia.replace(".", ","),
              plan: plans.data?.results.find((p) => p.code === ins.data!.plano)?.id })}>Lançar aporte de insuficiência</Button>
          )}
        </>}
        {ins.error && <span className="text-muted-foreground">{(ins.error as Error).message}</span>}
      </Card>
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Competência</TableHead><TableHead>Tipo</TableHead><TableHead>Plano</TableHead><TableHead className="text-right">Devido</TableHead><TableHead className="text-right">Pago</TableHead><TableHead>Vencimento</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={8} />}
            {data?.results.map((a) => (
              <TableRow key={a.id}>
                <TableCell>{compLabel(a.competence)}</TableCell><TableCell className="text-xs">{a.kind_display}<div className="text-2xs text-muted-foreground">{a.legal_basis}</div></TableCell>
                <TableCell><Badge variant="info">{a.plan_code}</Badge></TableCell>
                <TableCell className="text-right tabular">{formatCurrency(a.amount)}</TableCell><TableCell className="text-right tabular">{formatCurrency(a.paid)}</TableCell>
                <TableCell>{formatDate(a.due_date)}</TableCell><TableCell><SituationBadge s={a.situation} /></TableCell>
                <TableCell>{can("arrecadacao.aportes", "editar") && a.situation !== "PAGO" && <Button size="sm" variant="outline" onClick={() => setPaying(a)}>Baixar</Button>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={8} text="Nenhum aporte." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {creating && (
        <FormDialog title="Novo aporte" size="md" onClose={() => setCreating(null)} initial={creating}
          fields={[
            { name: "plan", label: "Plano", type: "select", required: true, options: (plans.data?.results ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.name}` })) },
            { name: "kind", label: "Tipo", type: "select", required: true, options: [
              { value: "DEFICIT", label: "Equacionamento do déficit atuarial" }, { value: "INSUFICIENCIA", label: "Insuficiência financeira" },
              { value: "COMPRA_VIDAS", label: "Compra de Vidas" }, { value: "OUTROS", label: "Outros" }] },
            { name: "competence", label: "Competência", type: "date", required: true },
            { name: "amount", label: "Valor (R$)", type: "money", required: true },
            { name: "due_date", label: "Vencimento", type: "date", required: true },
            { name: "legal_basis", label: "Fundamento legal", wide: true },
            { name: "notes", label: "Observações", type: "textarea" },
          ]}
          submit={async (body) => { await api("arrecadacao/aportes", { method: "POST", body }); toast.success("Aporte lançado."); mutate(); }} />
      )}
      {paying && <PayDialog title={`Baixa — ${paying.kind_display} ${compLabel(paying.competence)}`} path={`arrecadacao/aportes/${paying.id}/pay`}
        planId={paying.plan} suggested={(Number(paying.amount) - Number(paying.paid)).toFixed(2)} onClose={() => setPaying(null)} onDone={() => mutate()} />}
    </>
  );
}

// ------------------------------------------------------------------ Parcelamentos
type Agreement = {
  id: string; plan: string; plan_code: string; organ_name: string; number: string; cadprev_number: string; signed_date: string;
  principal: string; installments: number; first_due: string; index_display: string; monthly_interest: string; status: string;
  status_display: string; debt_period: string; progress: { pagas: number; em_atraso: number; total: number };
};
type Parcel = { id: string; number: number; due_date: string; amount: string; paid: string; situation: string };

export function AgreementsPage() {
  return <RequirePermission module="arrecadacao.parcelamentos"><Agreements /></RequirePermission>;
}

function Agreements() {
  const { can } = useSession();
  const plans = usePlans();
  const organs = useSWR<Paginated<{ id: string; name: string }>>("organs?ativos=1&page_size=200", fetcher);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<Agreement | null>(null);
  const { data, error, mutate } = useSWR<Paginated<Agreement>>(`arrecadacao/parcelamentos${qs({ page })}`, fetcher);
  const fields: FieldDef[] = [
    { name: "plan", label: "Plano", type: "select", required: true, options: (plans.data?.results ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.name}` })) },
    { name: "organ", label: "Órgão devedor", type: "select", required: true, options: (organs.data?.results ?? []).map((o) => ({ value: o.id, label: o.name })) },
    { name: "number", label: "Nº do termo", required: true },
    { name: "cadprev_number", label: "Nº no CADPREV" },
    { name: "signed_date", label: "Data do termo", type: "date", required: true },
    { name: "legal_basis", label: "Lei autorizativa" },
    { name: "principal", label: "Valor consolidado (R$)", type: "money", required: true },
    { name: "installments", label: "Nº de parcelas", type: "number", required: true },
    { name: "first_due", label: "Vencimento da 1ª parcela", type: "date", required: true },
    { name: "index", label: "Índice de atualização", type: "select", required: true, options: [{ value: "IPCA", label: "IPCA" }, { value: "INPC", label: "INPC" }, { value: "SELIC", label: "SELIC" }, { value: "NENHUM", label: "Nenhum" }] },
    { name: "monthly_interest", label: "Juros ao mês (%)" },
    { name: "debt_period", label: "Competências parceladas", wide: true },
  ];
  return (
    <>
      <PageHeader title="Parcelamentos" breadcrumb={crumbs("Parcelamentos")}
        description="Termos de acordo de parcelamento de débitos do ente (registrados no CADPREV). O cronograma é nominal; atualização e juros são informados na baixa de cada parcela."
        actions={can("arrecadacao.parcelamentos", "incluir") && <Button onClick={() => setCreating(true)}><Plus /> Novo parcelamento</Button>} />
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Termo</TableHead><TableHead>Devedor</TableHead><TableHead>Plano</TableHead><TableHead className="text-right">Consolidado</TableHead><TableHead>Parcelas</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={6} />}
            {data?.results.map((a) => (
              <TableRow key={a.id} className="cursor-pointer" onClick={() => setOpen(a)}>
                <TableCell className="font-medium text-primary">{a.number}<div className="text-2xs text-muted-foreground">{formatDate(a.signed_date)}{a.cadprev_number ? ` · CADPREV ${a.cadprev_number}` : ""}</div></TableCell>
                <TableCell>{a.organ_name}</TableCell><TableCell><Badge variant="info">{a.plan_code}</Badge></TableCell>
                <TableCell className="text-right tabular">{formatCurrency(a.principal)}</TableCell>
                <TableCell className="text-xs">{a.progress.pagas}/{a.progress.total} pagas{a.progress.em_atraso ? <Badge variant="critical" className="ml-1">{a.progress.em_atraso} em atraso</Badge> : null}</TableCell>
                <TableCell>{a.status_display}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum parcelamento." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {creating && (
        <FormDialog title="Novo parcelamento" size="lg" fields={fields} onClose={() => setCreating(false)} initial={{ index: "IPCA", monthly_interest: "0" }}
          submit={async (body) => { await api("arrecadacao/parcelamentos", { method: "POST", body }); toast.success("Parcelamento cadastrado e cronograma gerado."); mutate(); }} />
      )}
      {open && <AgreementDialog a={open} onClose={() => setOpen(null)} onChanged={() => mutate()} />}
    </>
  );
}

function AgreementDialog({ a, onClose, onChanged }: { a: Agreement; onClose: () => void; onChanged: () => void }) {
  const { can } = useSession();
  const { data, mutate } = useSWR<Parcel[]>(`arrecadacao/parcelamentos/${a.id}/parcels`, fetcher);
  const [paying, setPaying] = useState<Parcel | null>(null);
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Parcelamento {a.number} — {a.organ_name}</DialogTitle>
          <DialogDescription>{formatCurrency(a.principal)} em {a.installments} parcelas · {a.index_display}{Number(a.monthly_interest) ? ` + ${br(a.monthly_interest)}% a.m.` : ""} · {a.debt_period}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <Table>
            <TableHeader><TableRow><TableHead>Parcela</TableHead><TableHead>Vencimento</TableHead><TableHead className="text-right">Nominal</TableHead><TableHead className="text-right">Pago</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {!data && <LoadingRows cols={6} />}
              {data?.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.number}/{a.installments}</TableCell><TableCell>{formatDate(p.due_date)}</TableCell>
                  <TableCell className="text-right tabular">{formatCurrency(p.amount)}</TableCell><TableCell className="text-right tabular">{formatCurrency(p.paid)}</TableCell>
                  <TableCell><SituationBadge s={p.situation} /></TableCell>
                  <TableCell>{can("arrecadacao.parcelamentos", "editar") && p.situation !== "PAGO" && <Button size="sm" variant="outline" onClick={() => setPaying(p)}>Baixar</Button>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </DialogBody>
      </DialogContent>
      {paying && <PayDialog title={`Baixa — parcela ${paying.number}/${a.installments}`} path={`arrecadacao/parcelamentos/${a.id}/parcels/${paying.id}/pay`}
        planId={a.plan} suggested={paying.amount} onClose={() => setPaying(null)} onDone={() => { mutate(); onChanged(); }} />}
    </Dialog>
  );
}

// ------------------------------------------------------------------ Receitas
type RevenueRow = { id: string; plan: string; plan_code: string; kind: string; kind_display: string; date: string; competence: string | null; amount: string; fines: string; account_label: string; description: string; document: string; active: boolean };

export function RevenuesPage() {
  return <RequirePermission module="arrecadacao.receitas"><Revenues /></RequirePermission>;
}

function Revenues() {
  const { can } = useSession();
  const plans = usePlans();
  const accounts = useAccounts();
  const [page, setPage] = useState(1);
  const [plan, setPlan] = useState("");
  const [kind, setKind] = useState("");
  const [creating, setCreating] = useState(false);
  const [reversing, setReversing] = useState<RevenueRow | null>(null);
  const { data, error, mutate } = useSWR<Paginated<RevenueRow>>(`arrecadacao/receitas${qs({ page, plan, kind })}`, fetcher);
  return (
    <>
      <PageHeader title="Receitas" breadcrumb={crumbs("Receitas")}
        description="Receitas realizadas por plano. Contribuições, aportes e parcelas entram pela baixa nas respectivas telas; aqui se lançam COMPREV, rendimentos e outras. Não há exclusão: estorno com justificativa."
        actions={can("arrecadacao.receitas", "incluir") && <Button onClick={() => setCreating(true)}><Plus /> Nova receita</Button>} />
      {error && <ErrorState error={error} />}
      <Card>
        <div className="flex flex-wrap gap-3 border-b px-4 py-2.5">
          <Select className="w-48" value={plan} onChange={(e) => { setPlan(e.target.value); setPage(1); }} aria-label="Plano">
            <option value="">Todos os planos</option>{plans.data?.results.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
          </Select>
          <Select className="w-56" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} aria-label="Tipo">
            <option value="">Todos os tipos</option><option value="CONTRIBUICAO">Contribuições</option><option value="APORTE">Aportes</option>
            <option value="PARCELAMENTO">Parcelamentos</option><option value="COMPREV">COMPREV</option><option value="RENDIMENTOS">Rendimentos</option><option value="OUTRAS">Outras</option>
          </Select>
        </div>
        <Table>
          <TableHeader><TableRow><TableHead>Data</TableHead><TableHead>Receita</TableHead><TableHead>Plano</TableHead><TableHead>Competência</TableHead><TableHead className="text-right">Valor</TableHead><TableHead className="text-right">Encargos</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={7} />}
            {data?.results.map((r) => (
              <TableRow key={r.id} className={r.active ? "" : "opacity-50 line-through"}>
                <TableCell>{formatDate(r.date)}</TableCell>
                <TableCell className="text-xs"><b>{r.kind_display}</b> — {r.description}<div className="text-2xs text-muted-foreground">{r.document}{r.account_label ? ` · ${r.account_label}` : ""}</div></TableCell>
                <TableCell><Badge variant="info">{r.plan_code}</Badge></TableCell><TableCell>{compLabel(r.competence)}</TableCell>
                <TableCell className="text-right tabular">{formatCurrency(r.amount)}</TableCell><TableCell className="text-right tabular">{Number(r.fines) ? formatCurrency(r.fines) : "—"}</TableCell>
                <TableCell>{r.active && can("arrecadacao.receitas", "editar") && <Button size="icon" variant="ghost" className="h-7 w-7" title="Estornar" onClick={() => setReversing(r)}><Undo2 /></Button>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={7} text="Nenhuma receita." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {creating && (
        <FormDialog title="Nova receita" size="md" onClose={() => setCreating(false)} initial={{ kind: "RENDIMENTOS", date: new Date().toISOString().slice(0, 10) }}
          fields={[
            { name: "plan", label: "Plano", type: "select", required: true, options: (plans.data?.results ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.name}` })) },
            { name: "kind", label: "Tipo", type: "select", required: true, options: [{ value: "COMPREV", label: "COMPREV" }, { value: "RENDIMENTOS", label: "Rendimentos de aplicações" }, { value: "OUTRAS", label: "Outras receitas" }] },
            { name: "date", label: "Data do crédito", type: "date", required: true },
            { name: "competence", label: "Competência (1º dia)", type: "date" },
            { name: "amount", label: "Valor (R$)", type: "money", required: true },
            { name: "account", label: "Conta (mesmo plano)", type: "select", options: (accounts.data?.results ?? []).map((a) => ({ value: a.id, label: a.label })) },
            { name: "document", label: "Documento" },
            { name: "description", label: "Descrição", wide: true },
          ]}
          submit={async (body) => { await api("arrecadacao/receitas", { method: "POST", body }); toast.success("Receita lançada."); mutate(); }} />
      )}
      <ConfirmDialog open={!!reversing} onOpenChange={(v) => !v && setReversing(null)} title="Estornar a receita?" requireJustification destructive confirmLabel="Estornar"
        description={reversing ? `${reversing.kind_display} — ${formatCurrency(reversing.amount)} em ${formatDate(reversing.date)}` : ""}
        onConfirm={async (j) => {
          try {
            await api(`arrecadacao/receitas/${reversing!.id}/reverse`, { method: "POST", body: { justification: j } });
            toast.success("Receita estornada.");
            mutate();
          } catch (err) {
            toast.error((err as Error).message);
            throw err;
          }
        }} />
    </>
  );
}

// ------------------------------------------------------------------ Conciliação (devido × pago) e divergências
type RecRow = { id: string; plano: string; orgao: string; tipo: string; base: string; devido: string; pago: string; diferenca: string; vencimento: string; ultimo_pagamento: string | null; dias_atraso: number; situacao: string; origem: string };

export function CollectionReconciliationPage() {
  return <RequirePermission module="arrecadacao.conciliacao"><CollectionRec /></RequirePermission>;
}

function CollectionRec() {
  const plans = usePlans();
  const [comp, setComp] = useState(new Date().toISOString().slice(0, 7));
  const [plan, setPlan] = useState("");
  const { data, error } = useSWR<RecRow[]>(comp.length === 7 ? `arrecadacao/conciliacao${qs({ competence: comp, plan })}` : null, fetcher);
  const tot = (k: "devido" | "pago" | "diferenca") => (data ?? []).reduce((s, r) => s + Number(r[k]), 0);
  return (
    <>
      <PageHeader title="Conciliação da Arrecadação" breadcrumb={crumbs("Conciliação")}
        description="Devido × pago por órgão, plano e tipo de contribuição na competência."
        actions={data && data.length > 0 && <Button variant="outline" onClick={() => downloadCsv(`arrecadacao-${comp}.csv`,
          ["Plano", "Órgão", "Tipo", "Base", "Devido", "Pago", "Diferença", "Vencimento", "Último pagamento", "Dias de atraso", "Situação"],
          data.map((r) => [r.plano, r.orgao, r.tipo, br(r.base), br(r.devido), br(r.pago), br(r.diferenca), formatDate(r.vencimento), formatDate(r.ultimo_pagamento), r.dias_atraso, r.situacao]))}><Download /> Planilha</Button>} />
      <Card className="mb-3 flex flex-wrap gap-3 px-4 py-3">
        <Input type="month" className="w-44" value={comp} onChange={(e) => setComp(e.target.value)} aria-label="Competência" />
        <Select className="w-48" value={plan} onChange={(e) => setPlan(e.target.value)} aria-label="Plano">
          <option value="">Todos os planos</option>{plans.data?.results.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
        </Select>
      </Card>
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Órgão</TableHead><TableHead>Tipo</TableHead><TableHead>Plano</TableHead><TableHead className="text-right">Devido</TableHead><TableHead className="text-right">Pago</TableHead><TableHead className="text-right">Diferença</TableHead><TableHead>Vencimento</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={8} />}
            {data?.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{r.orgao}</TableCell><TableCell className="text-xs">{r.tipo}</TableCell><TableCell><Badge variant="info">{r.plano}</Badge></TableCell>
                <TableCell className="text-right tabular">{formatCurrency(r.devido)}</TableCell><TableCell className="text-right tabular">{formatCurrency(r.pago)}</TableCell>
                <TableCell className={`text-right tabular ${Number(r.diferenca) > 0 ? "text-critical" : ""}`}>{formatCurrency(r.diferenca)}</TableCell>
                <TableCell>{formatDate(r.vencimento)}{r.dias_atraso > 0 && <div className="text-2xs text-warning">pago com {r.dias_atraso} dia(s) de atraso</div>}</TableCell>
                <TableCell><SituationBadge s={r.situacao} /></TableCell>
              </TableRow>
            ))}
            {data?.length === 0 && <EmptyRow cols={8} text="Nenhuma contribuição na competência." />}
            {data && data.length > 0 && (
              <TableRow className="font-semibold"><TableCell colSpan={3}>Total</TableCell><TableCell className="text-right tabular">{formatCurrency(tot("devido"))}</TableCell>
                <TableCell className="text-right tabular">{formatCurrency(tot("pago"))}</TableCell><TableCell className="text-right tabular">{formatCurrency(tot("diferenca"))}</TableCell><TableCell colSpan={2} /></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}

type Div = { tipo: string; origem: string; id: string; plano: string; devedor: string; competencia: string; vencimento: string; devido: string; pago: string; diferenca: string; problema: string; dias: number };

export function DivergencesPage() {
  return <RequirePermission module="arrecadacao.divergencias"><Divergences /></RequirePermission>;
}

function Divergences() {
  const { data, error } = useSWR<Div[]>("arrecadacao/divergencias", fetcher);
  return (
    <>
      <PageHeader title="Divergências" breadcrumb={crumbs("Divergências")}
        description="Contribuições, aportes e parcelas vencidos e não pagos, pagos a menor ou pagos com atraso."
        actions={data && data.length > 0 && <Button variant="outline" onClick={() => downloadCsv("divergencias.csv",
          ["Devedor", "Tipo", "Plano", "Competência", "Vencimento", "Devido", "Pago", "Diferença", "Problema", "Dias"],
          data.map((r) => [r.devedor, r.tipo, r.plano, r.competencia, formatDate(r.vencimento), br(r.devido), br(r.pago), br(r.diferenca), r.problema, r.dias]))}><Download /> Planilha</Button>} />
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Devedor</TableHead><TableHead>Tipo</TableHead><TableHead>Competência</TableHead><TableHead className="text-right">Devido</TableHead><TableHead className="text-right">Pago</TableHead><TableHead className="text-right">Diferença</TableHead><TableHead>Problema</TableHead></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={7} />}
            {data?.map((r) => (
              <TableRow key={`${r.origem}-${r.id}`}>
                <TableCell>{r.devedor} <Badge variant="info">{r.plano}</Badge></TableCell><TableCell className="text-xs">{r.tipo}</TableCell>
                <TableCell>{r.competencia}<div className="text-2xs text-muted-foreground">venc. {formatDate(r.vencimento)}</div></TableCell>
                <TableCell className="text-right tabular">{formatCurrency(r.devido)}</TableCell><TableCell className="text-right tabular">{formatCurrency(r.pago)}</TableCell>
                <TableCell className="text-right tabular text-critical">{formatCurrency(r.diferenca)}</TableCell>
                <TableCell><Badge variant={r.problema === "Não pago" ? "critical" : "warning"}>{r.problema}</Badge> <span className="text-2xs text-muted-foreground">{r.dias} dia(s)</span></TableCell>
              </TableRow>
            ))}
            {data?.length === 0 && <EmptyRow cols={7} text="Nenhuma divergência." />}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}
