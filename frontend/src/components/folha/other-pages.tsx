"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Plus, Printer } from "lucide-react";

import { PersonPicker } from "@/components/people/person-picker";
import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCPF, formatCurrency, formatDate } from "@/lib/format";
import type { PayrollEntryRow, PersonRow } from "@/lib/types";

import { PayslipDialog } from "./payslip";

const MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

// ------------------------------------------------------------------ Contracheques
export function PayslipsPage() {
  return <RequirePermission module="folha.contracheques"><Payslips /></RequirePermission>;
}

function Payslips() {
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const { data, error } = useSWR<Paginated<PayrollEntryRow>>(
    person ? `folha/contracheques${qs({ beneficiary: person.id, page })}` : null, fetcher);
  return (
    <>
      <PageHeader title="Contracheques" breadcrumb={[{ label: "Folha de Benefícios" }, { label: "Contracheques" }]}
        description="Demonstrativos de pagamento por beneficiário. Para ver todos os contracheques de uma folha, abra a folha em Folha Mensal." />
      <Card className="mb-3 p-4"><div className="max-w-md"><PersonPicker value={person} onChange={(p) => { setPerson(p); setPage(1); }} /></div></Card>
      {error && <ErrorState error={error} />}
      {person && (
        <Card>
          <Table>
            <TableHeader><TableRow><TableHead>Contracheque</TableHead><TableHead className="text-right">Proventos</TableHead><TableHead className="text-right">Descontos</TableHead><TableHead className="text-right">Líquido</TableHead></TableRow></TableHeader>
            <TableBody>
              {!data && <LoadingRows cols={4} />}
              {data?.results.map((e) => (
                <TableRow key={e.id} className="cursor-pointer" onClick={() => setOpen(e.id)}>
                  <TableCell><span className="font-medium text-primary">{e.competencia}</span> · {e.run_kind} · <Badge variant="neutral">{e.folha}</Badge> <span className="text-2xs text-muted-foreground">{e.kind === "PENSAO" ? "Pensão" : "Aposentadoria"}</span></TableCell>
                  <TableCell className="text-right tabular">{formatCurrency(e.gross)}</TableCell>
                  <TableCell className="text-right tabular">{formatCurrency(e.discounts)}</TableCell>
                  <TableCell className="text-right tabular font-medium">{formatCurrency(e.net)}</TableCell>
                </TableRow>
              ))}
              {data?.results.length === 0 && <EmptyRow cols={4} text="Nenhum contracheque para este beneficiário." />}
            </TableBody>
          </Table>
          {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
        </Card>
      )}
      {open && <PayslipDialog id={open} onClose={() => setOpen(null)} />}
    </>
  );
}

// ------------------------------------------------------------------ Retroativos
type RetroRow = { id: string; run: string; competencia: string; folha: string; status: string; beneficiario: string; valor: string; irrf_rra: string; meses: { competencia: string; dias: number; valor: string; contribuicao: string }[] };

export function RetroactivesPage() {
  return <RequirePermission module="folha.retroativos"><Retro /></RequirePermission>;
}

function Retro() {
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const { data, error } = useSWR<Paginated<RetroRow>>(`folha/retroativos${qs({ page })}`, fetcher);
  return (
    <>
      <PageHeader title="Retroativos" breadcrumb={[{ label: "Folha de Benefícios" }, { label: "Retroativos" }]}
        description="Calculados automaticamente na primeira folha de cada benefício concedido no SIST: meses desde o início do benefício. Meses de anos anteriores são tributados como RRA (Lei 7.713/1988, art. 12-A). Para outros acertos, use Diferenças." />
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Competência</TableHead><TableHead>Beneficiário</TableHead><TableHead>Meses</TableHead><TableHead className="text-right">Retroativo</TableHead><TableHead className="text-right">IRRF RRA</TableHead><TableHead>Folha</TableHead></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={6} />}
            {data?.results.map((r) => (
              <TableRow key={r.id} className="cursor-pointer" onClick={() => setOpen(r.id)}>
                <TableCell>{r.competencia} <Badge variant="neutral">{r.folha}</Badge></TableCell>
                <TableCell className="font-medium text-primary">{r.beneficiario}</TableCell>
                <TableCell className="text-2xs">{r.meses.map((m) => `${m.competencia}${m.dias < 30 ? ` (${m.dias}d)` : ""}`).join(", ")}</TableCell>
                <TableCell className="text-right tabular">{formatCurrency(r.valor)}</TableCell>
                <TableCell className="text-right tabular">{Number(r.irrf_rra) ? formatCurrency(r.irrf_rra) : "—"}</TableCell>
                <TableCell><Link className="text-primary hover:underline" href={`/folha/folha-mensal/${r.run}`} onClick={(e) => e.stopPropagation()}>{r.status}</Link></TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum retroativo calculado." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {open && <PayslipDialog id={open} onClose={() => setOpen(null)} />}
    </>
  );
}

// ------------------------------------------------------------------ Informe de rendimentos
type Informe = {
  ano_calendario: number; beneficiario: string; cpf: string; fonte_pagadora: { nome: string; cnpj: string };
  quadro_3: Record<string, string>; quadro_4: Record<string, string>; quadro_5: Record<string, string>;
  rra: { rendimento: string; contribuicao: string; irrf: string; meses: number } | null; competencias: string[];
};

export function IncomeReportPage() {
  return <RequirePermission module="folha.informe_rendimentos"><Income /></RequirePermission>;
}

function Income() {
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [year, setYear] = useState(String(new Date().getFullYear() - 1));
  const { data, error } = useSWR<Informe>(person && year.length === 4 ? `folha/informe-rendimentos${qs({ person: person.id, year })}` : null, fetcher);
  const line = (label: string, v?: string) => (
    <div className="flex justify-between border-b py-1 last:border-0"><span>{label}</span><span className="tabular">{formatCurrency(v ?? "0")}</span></div>
  );
  return (
    <>
      <PageHeader title="Informe de Rendimentos" breadcrumb={[{ label: "Folha de Benefícios" }, { label: "Informe de Rendimentos" }]}
        description="Comprovante de rendimentos pagos e de IRRF (modelo da Receita Federal). Considera as folhas FECHADAS ou PAGAS do ano."
        actions={data && <Button variant="outline" onClick={() => window.print()}><Printer /> Imprimir</Button>} />
      <Card className="mb-3 grid gap-3 p-4 sm:grid-cols-[1fr_140px] print:hidden">
        <div><div className="mb-1 text-xs font-medium text-foreground/80">Beneficiário</div><PersonPicker value={person} onChange={setPerson} /></div>
        <FormField label="Ano-calendário" htmlFor="ir-year"><Input id="ir-year" inputMode="numeric" maxLength={4} value={year} onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))} /></FormField>
      </Card>
      {error && <ErrorState error={error} />}
      {data && (
        <Card className="space-y-4 p-5 text-xs">
          <div className="text-center"><div className="text-sm font-semibold">Comprovante de Rendimentos Pagos e de Imposto sobre a Renda Retido na Fonte</div><div>Ano-calendário {data.ano_calendario}</div></div>
          <section><div className="section-label mb-1">1. Fonte pagadora</div><div>{data.fonte_pagadora.nome} · CNPJ {data.fonte_pagadora.cnpj || "não cadastrado"}</div></section>
          <section><div className="section-label mb-1">2. Pessoa física beneficiária</div><div>{data.beneficiario} · CPF {formatCPF(data.cpf)} · Natureza: proventos de aposentadoria, reforma ou pensão</div></section>
          <section><div className="section-label mb-1">3. Rendimentos tributáveis, deduções e imposto retido</div>
            {line("1. Total dos rendimentos (inclusive férias)", data.quadro_3["1_rendimentos_tributaveis"])}
            {line("2. Contribuição previdenciária oficial", data.quadro_3["2_contribuicao_previdenciaria_oficial"])}
            {line("4. Pensão alimentícia", data.quadro_3["4_pensao_alimenticia"])}
            {line("5. Imposto sobre a renda retido na fonte", data.quadro_3["5_irrf"])}
          </section>
          <section><div className="section-label mb-1">4. Rendimentos isentos e não tributáveis</div>
            {line("1. Parcela isenta de aposentadoria/pensão (65 anos ou mais), inclusive 13º", data.quadro_4["1_parcela_isenta_65_anos"])}
            {line("3. Pensão e proventos de aposentadoria por moléstia grave", data.quadro_4["3_molestia_grave"])}
          </section>
          <section><div className="section-label mb-1">5. Rendimentos sujeitos à tributação exclusiva</div>
            {line("1. Décimo terceiro salário (líquido de deduções)", data.quadro_5["1_decimo_terceiro"])}
            {line("2. Imposto sobre a renda retido sobre o 13º", data.quadro_5["2_irrf_decimo_terceiro"])}
          </section>
          {data.rra && (
            <section><div className="section-label mb-1">6. Rendimentos recebidos acumuladamente (art. 12-A da Lei 7.713/1988)</div>
              {line(`Total dos rendimentos (${data.rra.meses} meses)`, data.rra.rendimento)}
              {line("Contribuição previdenciária oficial", data.rra.contribuicao)}
              {line("Imposto retido", data.rra.irrf)}
            </section>
          )}
          <div className="text-2xs text-muted-foreground">Competências consideradas: {data.competencias.join(", ") || "nenhuma folha fechada no ano"}.</div>
        </Card>
      )}
    </>
  );
}

// ------------------------------------------------------------------ Isenções de IR (moléstia grave)
type Exemption = { id: string; person: string; person_name: string; start: string; end: string | null; disease: string; report: string; active: boolean };

export function IrExemptionsPage() {
  return <RequirePermission module="folha.beneficiarios"><Exemptions /></RequirePermission>;
}

function Exemptions() {
  const { can } = useSession();
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const { data, error, mutate } = useSWR<Paginated<Exemption>>(`folha/isencoes-ir${qs({ page })}`, fetcher);
  return (
    <>
      <PageHeader title="Isenção de IR — moléstia grave" breadcrumb={[{ label: "Folha de Benefícios" }, { label: "Isenção de IR" }]}
        description="Lei 7.713/1988, art. 6º, XIV: proventos de aposentadoria e pensão de portadores de moléstia grave, comprovada por laudo pericial de serviço médico oficial, são isentos de IRRF."
        actions={can("folha.beneficiarios", "incluir") && <Button onClick={() => setAdding(true)}><Plus /> Nova isenção</Button>} />
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Beneficiário</TableHead><TableHead>Moléstia</TableHead><TableHead>Laudo</TableHead><TableHead>Vigência</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={5} />}
            {data?.results.map((x) => (
              <TableRow key={x.id}>
                <TableCell className="font-medium">{x.person_name}</TableCell><TableCell>{x.disease}</TableCell><TableCell className="text-xs">{x.report}</TableCell>
                <TableCell className="text-xs">{formatDate(x.start)}{x.end ? ` a ${formatDate(x.end)}` : " (sem prazo)"}</TableCell>
                <TableCell>{x.active ? <Badge variant="success">Ativa</Badge> : <Badge variant="neutral">Inativa</Badge>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhuma isenção cadastrada." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {adding && <ExemptionDialog onClose={() => setAdding(false)} onSaved={() => mutate()} />}
    </>
  );
}

function ExemptionDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [f, setF] = useState({ disease: "", report: "", start: "", end: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!person) { toast.error("Escolha o beneficiário."); return; }
    setBusy(true);
    try {
      await api("folha/isencoes-ir", { method: "POST", body: { ...f, end: f.end || null, person: person.id } });
      toast.success("Isenção registrada. Vale a partir do próximo cálculo.");
      onSaved();
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="md">
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader><DialogTitle>Nova isenção de IR</DialogTitle></DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2"><div className="mb-1 text-xs font-medium text-foreground/80">Beneficiário</div><PersonPicker value={person} onChange={setPerson} /></div>
            <FormField label="Moléstia (art. 6º, XIV)" htmlFor="x-dis" required className="sm:col-span-2"><Input id="x-dis" required value={f.disease} onChange={(e) => setF({ ...f, disease: e.target.value })} /></FormField>
            <FormField label="Laudo pericial (órgão oficial, nº e data)" htmlFor="x-rep" required className="sm:col-span-2"><Input id="x-rep" required value={f.report} onChange={(e) => setF({ ...f, report: e.target.value })} /></FormField>
            <FormField label="Início da isenção" htmlFor="x-start" required><Input id="x-start" type="date" required value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></FormField>
            <FormField label="Fim (laudo com validade)" htmlFor="x-end"><Input id="x-end" type="date" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></FormField>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Salvar</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
export const monthShort = (m: number) => MONTHS[m - 1];
