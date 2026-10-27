"use client";

/**
 * COMPREV — controle da compensação previdenciária. O requerimento e o pagamento acontecem no sistema COMPREV do
 * governo; aqui a equipe acompanha a situação, o valor mensal deferido e confere o que foi recebido ou pago.
 */
import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { ArrowDownLeft, ArrowUpRight, Banknote, ListChecks, Loader2, Plus, Search, Undo2 } from "lucide-react";

import { compLabel, useAccounts, usePlans } from "@/components/financeiro/common";
import { PersonPicker } from "@/components/people/person-picker";
import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import type { PersonRow } from "@/lib/types";
import { cn } from "@/lib/utils";

type Dir = "RECEBER" | "PAGAR";
type Process = {
  id: string; direction: Dir; direction_display: string; counterpart_kind: "RGPS" | "RPPS"; counterpart_kind_display: string;
  counterpart_name: string; counterpart_cnpj: string; counterpart_cnpj_formatted: string; plan: string; plan_code: string;
  benefit_kind: string; benefit_kind_display: string; person: string; person_name: string; person_cpf: string;
  benefit: string | null; benefit_label: string; averbacao: string | null; averbacao_label: string; ctc: string | null; ctc_label: string;
  request_number: string; requested_at: string; benefit_start: string | null; rmi: string | null; origin_days: number | null;
  total_days: number | null; status: string; status_display: string; status_date: string | null; comp_start: string | null;
  backlog_amount: string; requirement_text: string; requirement_due: string | null; decision_reason: string; ended_at: string | null;
  notes: string; valor_vigente: string | null; valor_sugerido: string | null;
};
type Movement = {
  id: string; process: string; person_name: string; request_number: string; counterpart_name: string; plan: string; plan_code: string;
  direction: Dir; kind: string; kind_display: string; competence: string; expected: string | null; amount: string; date: string;
  document: string; revenue: string | null; active: boolean; reversal_reason: string; difference: string | null;
};
type History = {
  eventos: { id: string; date: string; status_from_display: string; status_to_display: string; note: string; user_name: string; created_at: string }[];
  valores: { id: string; valid_from: string; amount: string; reason: string }[];
  movimentos: Movement[];
};
type FlowRow = { process: string; direction: Dir; person: string; plan: string; counterpart: string; request_number: string; expected: string; realized: string; difference: string; registered: boolean };
type Flow = { competencia: string; linhas: FlowRow[]; totais: Record<Dir, { previsto: string; realizado: string; pendentes: number; atrasados?: string }>; saldo: string };

const VARIANT: Record<string, "default" | "info" | "success" | "warning" | "neutral" | "critical"> = {
  CADASTRADO: "neutral", ENVIADO: "info", EXIGENCIA: "warning", DEFERIDO: "success", INDEFERIDO: "critical", CESSADO: "neutral", CANCELADO: "neutral",
};
const STATUS: [string, string][] = [
  ["CADASTRADO", "Em cadastramento"], ["ENVIADO", "Enviado / em análise"], ["EXIGENCIA", "Em exigência"], ["DEFERIDO", "Deferido (compensando)"],
  ["INDEFERIDO", "Indeferido"], ["CESSADO", "Compensação cessada"], ["CANCELADO", "Cancelado"],
];
const NEXT: Record<string, string[]> = {
  CADASTRADO: ["ENVIADO", "CANCELADO"], ENVIADO: ["EXIGENCIA", "DEFERIDO", "INDEFERIDO", "CANCELADO"],
  EXIGENCIA: ["ENVIADO", "INDEFERIDO", "CANCELADO"], INDEFERIDO: ["ENVIADO"], DEFERIDO: ["CESSADO"], CESSADO: [], CANCELADO: [],
};
const ACTION_LABEL: Record<string, string> = {
  ENVIADO: "Marcar como enviado", EXIGENCIA: "Registrar exigência", DEFERIDO: "Registrar deferimento", INDEFERIDO: "Registrar indeferimento",
  CESSADO: "Cessar compensação", CANCELADO: "Cancelar requerimento",
};
const DIR_TEXT: Record<Dir, { short: string; help: string }> = {
  RECEBER: { short: "A receber", help: "Nós pagamos o benefício e cobramos do regime onde o servidor também contribuiu (INSS ou outro RPPS)." },
  PAGAR: { short: "A pagar", help: "O servidor contribuiu aqui e se aposentou em outro regime, que nos cobra a parte deste tempo." },
};
const today = () => new Date().toISOString().slice(0, 10);
const thisMonth = () => today().slice(0, 7);
const prevMonth = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return d.toISOString().slice(0, 7); };
/** "1.234,56" ou "1234.56" → "1234.56" */
const money = (v: string) => { const s = v.trim(); return s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : s; };
const toBR = (v: string | null | undefined) => (v ? v.replace(".", ",") : "");

function DirSwitch({ value, onChange }: { value: Dir; onChange: (d: Dir) => void }) {
  return (
    <div className="inline-flex rounded-md border bg-card p-0.5">
      {(["RECEBER", "PAGAR"] as Dir[]).map((d) => (
        <button key={d} type="button" onClick={() => onChange(d)}
          className={cn("flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium", value === d ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
          {d === "RECEBER" ? <ArrowDownLeft className="h-3.5 w-3.5" /> : <ArrowUpRight className="h-3.5 w-3.5" />}{DIR_TEXT[d].short}
        </button>
      ))}
    </div>
  );
}

// ============================================================ Processos
export function ComprevProcessesPage() {
  return <RequirePermission module="comprev.processos"><Processes /></RequirePermission>;
}

function Processes() {
  const { can } = useSession();
  const router = useRouter();
  const sp = useSearchParams();
  const sel = sp.get("p");
  const [dir, setDir] = useState<Dir>((sp.get("sentido") as Dir) || "RECEBER");
  const [status, setStatus] = useState("");
  const [term, setTerm] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState<{ person?: string; benefit?: string } | null>(null);
  useEffect(() => { const t = setTimeout(() => { setSearch(term); setPage(1); }, 300); return () => clearTimeout(t); }, [term]);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Process>>(
    `comprev/processos${qs({ sentido: dir, situacao: status, search, page })}`, fetcher, { keepPreviousData: true });
  const potential = useSWR<{ benefit: string; kind: string; beneficiary: string; person: string; person_name: string; person_cpf: string; start_date: string; amount: string; plan: string }[]>(
    dir === "RECEBER" ? "comprev/processos/potencial" : null, fetcher);
  const current = useSWR<Process>(sel ? `comprev/processos/${sel}` : null, fetcher);

  return (
    <>
      <PageHeader title="Processos COMPREV" description="Requerimentos de compensação previdenciária feitos no sistema COMPREV do governo. Aqui você acompanha a situação, o valor deferido e os prazos de exigência."
        breadcrumb={[{ label: "COMPREV" }, { label: "Processos" }]}
        actions={can("comprev.processos", "incluir") && <Button onClick={() => setCreating({})}><Plus /> Novo requerimento</Button>} />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <DirSwitch value={dir} onChange={(d) => { setDir(d); setPage(1); router.replace(`?sentido=${d}`); }} />
        <span className="text-xs text-muted-foreground">{DIR_TEXT[dir].help}</span>
      </div>
      {dir === "RECEBER" && (potential.data?.length ?? 0) > 0 && (
        <Card className="mb-4 border-warning-border bg-warning-soft/40">
          <CardHeader><CardTitle>Benefícios com tempo de outro regime ainda sem requerimento ({potential.data!.length})</CardTitle></CardHeader>
          <CardContent className="space-y-1.5 text-xs">
            <p className="text-muted-foreground">O segurado (ou o instituidor da pensão) tem tempo averbado do INSS ou de outro RPPS marcado como sujeito ao COMPREV. Dinheiro que o órgão pode estar deixando de receber.</p>
            {potential.data!.slice(0, 5).map((b) => (
              <div key={b.benefit} className="flex flex-wrap items-center justify-between gap-2 rounded border bg-card px-3 py-1.5">
                <span><b>{b.person_name}</b> · {b.kind}{b.beneficiary !== b.person_name ? ` (${b.beneficiary})` : ""} desde {formatDate(b.start_date)} · {formatCurrency(b.amount)} · {b.plan}</span>
                {can("comprev.processos", "incluir") && <Button size="sm" variant="outline" onClick={() => setCreating({ person: b.person, benefit: b.benefit })}>Criar requerimento</Button>}
              </div>
            ))}
            {potential.data!.length > 5 && <p className="text-muted-foreground">… e mais {potential.data!.length - 5}. Veja o relatório “Benefícios sem requerimento COMPREV”.</p>}
          </CardContent>
        </Card>
      )}
      <div className="grid gap-4 xl:grid-cols-12">
        <Card className={cn("self-start", sel ? "xl:col-span-6" : "xl:col-span-12")}>
          <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
            <div className="relative w-64"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-8" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Nome, CPF, nº ou regime" /></div>
            <Select className="w-52" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
              <option value="">Todas as situações</option>{STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </div>
          {error && <div className="p-4"><ErrorState error={error} /></div>}
          <Table>
            <TableHeader><TableRow><TableHead>Segurado / instituidor</TableHead><TableHead>Outro regime</TableHead><TableHead>Nº COMPREV</TableHead><TableHead>Situação</TableHead><TableHead className="text-right">Valor mensal</TableHead></TableRow></TableHeader>
            <TableBody>
              {isLoading && !data && <LoadingRows cols={5} />}
              {data?.results.map((p) => (
                <TableRow key={p.id} className={cn("cursor-pointer", sel === p.id && "bg-primary-soft")} onClick={() => router.replace(`?sentido=${dir}&p=${p.id}`)}>
                  <TableCell><div className="font-medium text-primary">{p.person_name}</div><div className="text-2xs text-muted-foreground">{p.benefit_kind_display} · {p.plan_code} · requerido em {formatDate(p.requested_at)}</div></TableCell>
                  <TableCell className="text-xs">{p.counterpart_name}</TableCell>
                  <TableCell className="text-xs">{p.request_number || "—"}</TableCell>
                  <TableCell><Badge variant={VARIANT[p.status]}>{p.status_display}</Badge>
                    {p.status === "EXIGENCIA" && p.requirement_due && <div className="mt-0.5 text-2xs text-warning">prazo {formatDate(p.requirement_due)}</div>}</TableCell>
                  <TableCell className="text-right tabular">{p.valor_vigente ? formatCurrency(p.valor_vigente) : "—"}</TableCell>
                </TableRow>
              ))}
              {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum requerimento." />}
            </TableBody>
          </Table>
          {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
        </Card>
        {sel && current.data && (
          <div className="xl:col-span-6"><ProcessDetail p={current.data} onChanged={() => { current.mutate(); mutate(); potential.mutate(); }} /></div>
        )}
      </div>
      {creating && <ProcessDialog direction={dir} preset={creating} onClose={() => setCreating(null)}
        onSaved={(id) => { mutate(); potential.mutate(); router.replace(`?sentido=${dir}&p=${id}`); }} />}
    </>
  );
}

type Options = {
  beneficios: { id: string; label: string; kind: string; start_date: string; amount: string; plan: string; plan_code: string }[];
  averbacoes: { id: string; label: string; days: number; nature: string; issuer: string; issuer_cnpj: string }[];
  ctcs: { id: string; label: string; destination: string }[];
};

function ProcessDialog({ direction, preset, process, onClose, onSaved }: {
  direction: Dir; preset?: { person?: string; benefit?: string }; process?: Process; onClose: () => void; onSaved: (id: string) => void;
}) {
  const plans = usePlans();
  const [person, setPerson] = useState<PersonRow | null>(null);
  const personId = process?.person ?? person?.id ?? preset?.person ?? "";
  const presetPerson = useSWR<PersonRow>(!process && preset?.person && !person ? `people/${preset.person}` : null, fetcher);
  useEffect(() => { if (presetPerson.data) setPerson(presetPerson.data); }, [presetPerson.data]);
  const opts = useSWR<Options>(personId ? `comprev/processos/opcoes?pessoa=${personId}` : null, fetcher);
  const decided = process && !["CADASTRADO", "ENVIADO", "EXIGENCIA"].includes(process.status);
  const [f, setF] = useState(() => ({
    counterpart_kind: process?.counterpart_kind ?? (direction === "RECEBER" ? "RGPS" : "RPPS"),
    counterpart_name: process?.counterpart_name ?? "", counterpart_cnpj: process?.counterpart_cnpj_formatted ?? "",
    benefit: process?.benefit ?? preset?.benefit ?? "", averbacao: process?.averbacao ?? "", ctc: process?.ctc ?? "",
    plan: process?.plan ?? "", benefit_kind: process?.benefit_kind ?? "APOSENTADORIA",
    request_number: process?.request_number ?? "", requested_at: process?.requested_at ?? today(),
    benefit_start: process?.benefit_start ?? "", rmi: toBR(process?.rmi), origin_days: String(process?.origin_days ?? ""),
    total_days: String(process?.total_days ?? ""), notes: process?.notes ?? "",
  }));
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));
  const [busy, setBusy] = useState(false);
  const benefit = opts.data?.beneficios.find((b) => b.id === f.benefit);
  // Ao escolher a averbação, sugere o tempo de origem e o regime
  const pickAverbacao = (id: string) => {
    const a = opts.data?.averbacoes.find((x) => x.id === id);
    setF((x) => ({
      ...x, averbacao: id,
      origin_days: a && !x.origin_days ? String(a.days) : x.origin_days,
      counterpart_kind: a ? (["01", "02"].includes(a.nature) ? "RGPS" : "RPPS") : x.counterpart_kind,
      counterpart_name: a && !["01", "02"].includes(a.nature) && !x.counterpart_name ? a.issuer : x.counterpart_name,
      counterpart_cnpj: a && !["01", "02"].includes(a.nature) && !x.counterpart_cnpj ? a.issuer_cnpj : x.counterpart_cnpj,
    }));
  };
  const save = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = decided ? { request_number: f.request_number, notes: f.notes } : {
        ...f, direction, person: personId, rmi: f.rmi ? money(f.rmi) : null,
        origin_days: f.origin_days || null, total_days: f.total_days || null, benefit_start: f.benefit_start || null,
        benefit: direction === "RECEBER" ? f.benefit || null : null, averbacao: direction === "RECEBER" ? f.averbacao || null : null,
        ctc: direction === "PAGAR" ? f.ctc || null : null, plan: f.plan || (benefit?.plan ?? null),
      };
      const r = process ? await api<Process>(`comprev/processos/${process.id}`, { method: "PATCH", body })
        : await api<Process>("comprev/processos", { method: "POST", body });
      toast.success(process ? "Requerimento atualizado." : "Requerimento cadastrado.");
      onSaved(r.id);
      onClose();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{process ? "Editar requerimento" : `Novo requerimento — ${DIR_TEXT[direction].short.toLowerCase()}`}</DialogTitle>
          <DialogDescription>{DIR_TEXT[direction].help} Copie os dados do requerimento feito no sistema COMPREV.</DialogDescription>
        </DialogHeader>
        <DialogBody className="grid gap-3 sm:grid-cols-2">
          {decided ? (
            <p className="rounded border bg-muted/40 p-2 text-xs sm:col-span-2">Requerimento já decidido: só o nº do requerimento e as observações podem ser alterados.</p>
          ) : <>
            <FormField label={direction === "RECEBER" ? "Segurado (na pensão, o instituidor)" : "Ex-servidor (segurado)"} required className="sm:col-span-2">
              {process ? <div className="text-sm font-medium">{process.person_name}</div> : <PersonPicker value={person} onChange={setPerson} />}
            </FormField>
            {direction === "RECEBER" ? <>
              <FormField label="Benefício pago por nós" className="sm:col-span-2" hint="O plano e o tipo de benefício vêm do benefício escolhido.">
                <Select value={f.benefit} onChange={(e) => set("benefit", e.target.value)} disabled={!personId}>
                  <option value="">{personId ? (opts.data?.beneficios.length ? "Selecione…" : "Nenhum benefício desta pessoa") : "Escolha a pessoa primeiro"}</option>
                  {opts.data?.beneficios.map((b) => <option key={b.id} value={b.id}>{b.label} · {b.plan_code}</option>)}
                </Select>
              </FormField>
              <FormField label="Averbação do tempo do outro regime" className="sm:col-span-2">
                <Select value={f.averbacao} onChange={(e) => pickAverbacao(e.target.value)} disabled={!personId}>
                  <option value="">{opts.data?.averbacoes.length ? "Selecione (opcional)…" : "Nenhuma averbação cadastrada"}</option>
                  {opts.data?.averbacoes.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
                </Select>
              </FormField>
            </> : <>
              <FormField label="CTC emitida por nós (opcional)" className="sm:col-span-2">
                <Select value={f.ctc} onChange={(e) => set("ctc", e.target.value)} disabled={!personId}>
                  <option value="">{opts.data?.ctcs.length ? "Selecione…" : "Nenhuma CTC emitida no sistema"}</option>
                  {opts.data?.ctcs.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </Select>
              </FormField>
              <FormField label="Benefício (no outro regime)" required>
                <Select value={f.benefit_kind} onChange={(e) => set("benefit_kind", e.target.value)}>
                  <option value="APOSENTADORIA">Aposentadoria</option><option value="PENSAO">Pensão por morte</option>
                </Select>
              </FormField>
              <FormField label="Plano que paga" required>
                <Select value={f.plan} onChange={(e) => set("plan", e.target.value)} required>
                  <option value="" disabled>Selecione…</option>{plans.data?.results.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
                </Select>
              </FormField>
            </>}
            <FormField label="Outro regime" required>
              <Select value={f.counterpart_kind} onChange={(e) => set("counterpart_kind", e.target.value)}>
                <option value="RGPS">RGPS (INSS)</option><option value="RPPS">Outro RPPS</option>
              </Select>
            </FormField>
            {f.counterpart_kind === "RPPS" ? <>
              <FormField label="CNPJ do outro RPPS" required><Input value={f.counterpart_cnpj} onChange={(e) => set("counterpart_cnpj", e.target.value)} inputMode="numeric" /></FormField>
              <FormField label="Nome do outro RPPS" required className="sm:col-span-2"><Input value={f.counterpart_name} onChange={(e) => set("counterpart_name", e.target.value)} /></FormField>
            </> : <div className="self-end pb-2 text-xs text-muted-foreground">Instituto Nacional do Seguro Social — INSS</div>}
            <FormField label="Data do requerimento" required><Input type="date" value={f.requested_at} onChange={(e) => set("requested_at", e.target.value)} /></FormField>
            <FormField label="Início do benefício (DIB)" hint={direction === "RECEBER" ? "Vazio = data do benefício escolhido" : undefined}><Input type="date" value={f.benefit_start} onChange={(e) => set("benefit_start", e.target.value)} /></FormField>
            <FormField label="Renda mensal inicial (R$)"><Input inputMode="decimal" value={f.rmi} onChange={(e) => set("rmi", e.target.value)} placeholder={benefit ? toBR(benefit.amount) : ""} /></FormField>
            <div className="grid grid-cols-2 gap-2">
              <FormField label="Tempo no regime de origem (dias)"><Input type="number" value={f.origin_days} onChange={(e) => set("origin_days", e.target.value)} /></FormField>
              <FormField label="Tempo total (dias)"><Input type="number" value={f.total_days} onChange={(e) => set("total_days", e.target.value)} /></FormField>
            </div>
          </>}
          <FormField label="Nº do requerimento no COMPREV" hint="Obrigatório para marcar como enviado."><Input value={f.request_number} onChange={(e) => set("request_number", e.target.value)} /></FormField>
          <FormField label="Observações" className="sm:col-span-2"><Textarea value={f.notes} onChange={(e) => set("notes", e.target.value)} /></FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} disabled={busy || (!process && !personId)}>{busy && <Loader2 className="animate-spin" />} Salvar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProcessDetail({ p, onChanged }: { p: Process; onChanged: () => void }) {
  const { can } = useSession();
  const hist = useSWR<History>(`comprev/processos/${p.id}/historico`, fetcher);
  const [next, setNext] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [newValue, setNewValue] = useState(false);
  const refresh = () => { hist.mutate(); onChanged(); };
  const canEdit = can("comprev.processos", "editar");
  const row = (label: string, value: React.ReactNode) => <div><span className="text-muted-foreground">{label}: </span>{value || "—"}</div>;
  return (
    <Card className="self-start">
      <CardHeader className="flex-wrap gap-2">
        <div><CardTitle>{p.person_name}</CardTitle><div className="text-2xs text-muted-foreground">CPF {p.person_cpf} · {p.direction_display}</div></div>
        <Badge variant={VARIANT[p.status]}>{p.status_display}</Badge>
      </CardHeader>
      <CardContent className="space-y-4 text-xs">
        <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
          {row("Outro regime", `${p.counterpart_name}${p.counterpart_cnpj_formatted ? ` (${p.counterpart_cnpj_formatted})` : ""}`)}
          {row("Nº COMPREV", p.request_number)}
          {row("Benefício", `${p.benefit_kind_display} · plano ${p.plan_code}`)}
          {row("Requerido em", formatDate(p.requested_at))}
          {p.benefit_label && row("Benefício pago por nós", p.benefit_label)}
          {p.averbacao_label && row("Averbação", p.averbacao_label)}
          {p.ctc_label && row("CTC", p.ctc_label)}
          {row("Início do benefício", formatDate(p.benefit_start))}
          {row("Renda mensal inicial", p.rmi ? formatCurrency(p.rmi) : "")}
          {row("Tempo (origem / total)", p.origin_days ? `${p.origin_days} / ${p.total_days ?? "?"} dias` : "")}
          {p.valor_sugerido && row("Pro rata calculado", <>{formatCurrency(p.valor_sugerido)} <span className="text-muted-foreground">(conferência; vale o deferido)</span></>)}
          {p.comp_start && row("Compensação", `desde ${compLabel(p.comp_start)}${p.ended_at ? ` até ${compLabel(p.ended_at)}` : ""}`)}
          {p.valor_vigente && row("Valor mensal vigente", <b>{formatCurrency(p.valor_vigente)}</b>)}
          {Number(p.backlog_amount) > 0 && row("Atrasados deferidos", formatCurrency(p.backlog_amount))}
        </div>
        {p.status === "EXIGENCIA" && <div className="rounded border border-warning-border bg-warning-soft p-2"><b>Exigência</b> (prazo {formatDate(p.requirement_due)}): {p.requirement_text}</div>}
        {p.decision_reason && ["INDEFERIDO", "CESSADO", "CANCELADO"].includes(p.status) && <div className="rounded border bg-muted/40 p-2"><b>Motivo:</b> {p.decision_reason}</div>}
        {p.notes && <div className="whitespace-pre-wrap rounded border bg-muted/30 p-2">{p.notes}</div>}
        {canEdit && (
          <div className="flex flex-wrap gap-2">
            {NEXT[p.status].map((s) => (
              <Button key={s} size="sm" variant={["CANCELADO", "INDEFERIDO", "CESSADO"].includes(s) ? "ghost" : s === "DEFERIDO" ? "default" : "outline"} onClick={() => setNext(s)}>
                {p.status === "EXIGENCIA" && s === "ENVIADO" ? "Exigência cumprida" : p.status === "INDEFERIDO" && s === "ENVIADO" ? "Reenviar / recurso" : ACTION_LABEL[s]}
              </Button>
            ))}
            {p.status === "DEFERIDO" && <Button size="sm" variant="outline" onClick={() => setNewValue(true)}>Novo valor (reajuste)</Button>}
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Editar dados</Button>
          </div>
        )}
        {hist.data && hist.data.valores.length > 0 && (
          <div><div className="mb-1 font-semibold text-primary-strong">Valor mensal (histórico)</div>
            <Table><TableHeader><TableRow><TableHead>A partir de</TableHead><TableHead className="text-right">Valor</TableHead><TableHead>Motivo</TableHead></TableRow></TableHeader>
              <TableBody>{hist.data.valores.map((v) => <TableRow key={v.id}><TableCell>{compLabel(v.valid_from)}</TableCell><TableCell className="text-right tabular">{formatCurrency(v.amount)}</TableCell><TableCell>{v.reason}</TableCell></TableRow>)}</TableBody></Table>
          </div>
        )}
        {hist.data && hist.data.movimentos.length > 0 && (
          <div><div className="mb-1 font-semibold text-primary-strong">{p.direction === "RECEBER" ? "Recebimentos" : "Pagamentos"}</div>
            <Table><TableHeader><TableRow><TableHead>Comp.</TableHead><TableHead>Tipo</TableHead><TableHead>Data</TableHead><TableHead className="text-right">Valor</TableHead></TableRow></TableHeader>
              <TableBody>{hist.data.movimentos.slice(0, 24).map((m) => (
                <TableRow key={m.id} className={cn(!m.active && "text-muted-foreground line-through")}>
                  <TableCell>{compLabel(m.competence)}</TableCell><TableCell>{m.kind_display}</TableCell><TableCell>{formatDate(m.date)}</TableCell>
                  <TableCell className="text-right tabular">{m.kind === "GLOSA" ? "−" : ""}{formatCurrency(m.amount)}</TableCell>
                </TableRow>))}</TableBody></Table>
          </div>
        )}
        {hist.data && (
          <div><div className="mb-1 font-semibold text-primary-strong">Andamento</div>
            <ol className="space-y-1 border-l pl-3">
              <li><span className="text-muted-foreground">{formatDate(p.requested_at)}</span> · requerimento cadastrado</li>
              {hist.data.eventos.map((e) => (
                <li key={e.id}><span className="text-muted-foreground">{formatDate(e.date)}</span> · {e.status_from_display} → <b>{e.status_to_display}</b>
                  {e.note && <> — {e.note}</>}<span className="text-2xs text-muted-foreground"> ({e.user_name || "—"}, {formatDateTime(e.created_at)})</span></li>
              ))}
            </ol>
          </div>
        )}
      </CardContent>
      {next && <StatusDialog p={p} status={next} onClose={() => setNext(null)} onDone={refresh} />}
      {editing && <ProcessDialog direction={p.direction} process={p} onClose={() => setEditing(false)} onSaved={refresh} />}
      {newValue && (
        <FormDialog title="Novo valor mensal" size="sm" onClose={() => setNewValue(false)}
          description="Reajuste ou revisão informados pelo COMPREV. O valor anterior fica no histórico."
          initial={{ valid_from: thisMonth() }}
          fields={[
            { name: "valid_from", label: "A partir da competência (AAAA-MM)", required: true },
            { name: "amount", label: "Novo valor mensal (R$)", type: "money", required: true },
            { name: "reason", label: "Motivo", type: "textarea", required: true, wide: true },
          ]}
          submitLabel="Salvar valor"
          submit={async (body) => { await api(`comprev/processos/${p.id}/valor`, { method: "POST", body }); toast.success("Valor registrado."); refresh(); }} />
      )}
    </Card>
  );
}

function StatusDialog({ p, status, onClose, onDone }: { p: Process; status: string; onClose: () => void; onDone: () => void }) {
  const fields: FieldDef[] = [{ name: "date", label: "Data", type: "date", required: true }];
  if (status === "EXIGENCIA") {
    fields.push({ name: "note", label: "O que foi exigido", type: "textarea", required: true, wide: true },
      { name: "requirement_due", label: "Prazo para cumprir", type: "date", required: true });
  } else if (status === "DEFERIDO") {
    fields.push({ name: "comp_start", label: "Início da compensação (AAAA-MM)", required: true, hint: "Primeira competência compensada" },
      { name: "amount", label: "Valor mensal deferido (R$)", type: "money", required: true, hint: p.valor_sugerido ? `Pro rata calculado: ${formatCurrency(p.valor_sugerido)}` : undefined },
      { name: "backlog", label: "Atrasados / estoque deferido (R$)", type: "money" },
      { name: "note", label: "Observação", type: "textarea", wide: true });
  } else if (status === "CESSADO") {
    fields.push({ name: "ended_at", label: "Última competência compensada (AAAA-MM)", required: true },
      { name: "note", label: "Motivo (óbito, revisão, cessação do benefício…)", type: "textarea", required: true, wide: true });
  } else if (["INDEFERIDO", "CANCELADO"].includes(status)) {
    fields.push({ name: "note", label: "Motivo", type: "textarea", required: true, wide: true });
  } else {
    fields.push({ name: "note", label: "Observação", type: "textarea", wide: true });
  }
  return (
    <FormDialog title={ACTION_LABEL[status] ?? "Situação"} size="md" fields={fields} onClose={onClose}
      description={status === "ENVIADO" && !p.request_number ? "Antes, informe o nº do requerimento no COMPREV (Editar dados)." : `Situação atual: ${p.status_display}. Fica registrado no andamento e na auditoria.`}
      initial={{ date: today(), comp_start: p.benefit_start ? p.benefit_start.slice(0, 7) : "", amount: toBR(p.valor_sugerido), ended_at: thisMonth() }}
      submitLabel="Confirmar"
      submit={async (body) => {
        await api(`comprev/processos/${p.id}/situacao`, { method: "POST", body: { ...body, status } });
        toast.success("Situação atualizada.");
        onDone();
      }} />
  );
}

// ============================================================ Recebimentos / Pagamentos
export function ComprevMovementsPage({ direction }: { direction: Dir }) {
  const mod = direction === "RECEBER" ? "comprev.recebimentos" : "comprev.pagamentos";
  return <RequirePermission module={mod}><Movements direction={direction} module={mod} /></RequirePermission>;
}

function Movements({ direction, module }: { direction: Dir; module: string }) {
  const { can } = useSession();
  const [comp, setComp] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [reversing, setReversing] = useState<Movement | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [toRevenue, setToRevenue] = useState(false);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Movement>>(
    `comprev/movimentos${qs({ sentido: direction, competencia: comp, page })}`, fetcher, { keepPreviousData: true });
  const title = direction === "RECEBER" ? "Recebimentos COMPREV" : "Pagamentos COMPREV";
  const pickable = (m: Movement) => direction === "RECEBER" && m.active && !m.revenue;
  const sel = data?.results.filter((m) => picked.has(m.id)) ?? [];
  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  return (
    <>
      <PageHeader title={title}
        description={direction === "RECEBER" ? "Valores que o COMPREV creditou ao órgão (somos o regime instituidor). Confira com o previsto e leve à receita do Financeiro." : "Valores que o órgão pagou pelo COMPREV a outros regimes (somos o regime de origem)."}
        breadcrumb={[{ label: "COMPREV" }, { label: direction === "RECEBER" ? "Recebimentos" : "Pagamentos" }]}
        actions={<div className="flex gap-2">
          {direction === "RECEBER" && sel.length > 0 && can("arrecadacao.receitas", "incluir") && <Button variant="outline" onClick={() => setToRevenue(true)}><Banknote /> Levar ao Financeiro ({sel.length})</Button>}
          {can(module, "incluir") && <Button onClick={() => setAdding(true)}><Plus /> Lançar</Button>}
        </div>} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <label className="flex items-center gap-2 text-xs">Competência <Input type="month" className="h-8 w-40" value={comp} onChange={(e) => { setComp(e.target.value); setPage(1); }} /></label>
          {comp && <Button size="sm" variant="ghost" onClick={() => setComp("")}>Todas</Button>}
          <span className="text-2xs text-muted-foreground">Para lançar o mês inteiro de uma vez, use COMPREV › Fluxo Mensal.</span>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow>
            {direction === "RECEBER" && <TableHead className="w-8" />}
            <TableHead>Comp.</TableHead><TableHead>Segurado / instituidor</TableHead><TableHead>Tipo</TableHead><TableHead>Data</TableHead><TableHead>Documento</TableHead>
            <TableHead className="text-right">Previsto</TableHead><TableHead className="text-right">Valor</TableHead><TableHead>Situação</TableHead><TableHead className="w-10" />
          </TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={10} />}
            {data?.results.map((m) => (
              <TableRow key={m.id} className={cn(!m.active && "text-muted-foreground")}>
                {direction === "RECEBER" && <TableCell>{pickable(m) && <input type="checkbox" checked={picked.has(m.id)} onChange={() => toggle(m.id)} aria-label="Selecionar" />}</TableCell>}
                <TableCell>{compLabel(m.competence)}</TableCell>
                <TableCell><div className="font-medium">{m.person_name}</div><div className="text-2xs text-muted-foreground">{m.counterpart_name} · {m.plan_code}</div></TableCell>
                <TableCell>{m.kind_display}</TableCell>
                <TableCell>{formatDate(m.date)}</TableCell>
                <TableCell className="text-xs">{m.document || "—"}</TableCell>
                <TableCell className="text-right tabular">{m.expected ? formatCurrency(m.expected) : "—"}</TableCell>
                <TableCell className="text-right tabular font-medium">{m.kind === "GLOSA" ? "−" : ""}{formatCurrency(m.amount)}
                  {m.difference && Number(m.difference) !== 0 && <div className={cn("text-2xs", Number(m.difference) < 0 ? "text-critical" : "text-success")}>dif. {formatCurrency(m.difference)}</div>}</TableCell>
                <TableCell>{!m.active ? <Badge variant="neutral" title={m.reversal_reason}>Estornado</Badge> : m.revenue ? <Badge variant="success">No Financeiro</Badge> : <Badge variant="info">Lançado</Badge>}</TableCell>
                <TableCell>{m.active && can(module, "editar") && <Button size="icon" variant="ghost" title="Estornar" onClick={() => setReversing(m)}><Undo2 /></Button>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={10} text="Nenhum lançamento." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {adding && <MovementDialog direction={direction} onClose={() => setAdding(false)} onDone={mutate} />}
      {reversing && (
        <FormDialog title="Estornar lançamento" size="sm" onClose={() => setReversing(null)}
          description={`${reversing.person_name} · ${compLabel(reversing.competence)} · ${formatCurrency(reversing.amount)}. O lançamento não é apagado: fica marcado como estornado.`}
          fields={[{ name: "reason", label: "Motivo", type: "textarea", required: true, wide: true }]} submitLabel="Estornar"
          submit={async (body) => { await api(`comprev/movimentos/${reversing.id}/estornar?sentido=${direction}`, { method: "POST", body }); toast.success("Lançamento estornado."); mutate(); }} />
      )}
      {toRevenue && <RevenueDialog items={sel} onClose={() => setToRevenue(false)} onDone={() => { setPicked(new Set()); mutate(); }} />}
    </>
  );
}

function MovementDialog({ direction, onClose, onDone }: { direction: Dir; onClose: () => void; onDone: () => void }) {
  const procs = useSWR<Paginated<Process>>(`comprev/processos?sentido=${direction}&situacao=DEFERIDO,CESSADO&page_size=500`, fetcher);
  const fields: FieldDef[] = [
    { name: "process", label: "Requerimento", type: "select", required: true, wide: true,
      options: (procs.data?.results ?? []).map((p) => ({ value: p.id, label: `${p.person_name} — ${p.counterpart_name}${p.valor_vigente ? ` (${formatCurrency(p.valor_vigente)}/mês)` : ""}` })) },
    { name: "kind", label: "Tipo", type: "select", required: true, options: [
      { value: "MENSAL", label: "Fluxo mensal" }, { value: "ATRASADOS", label: "Atrasados / estoque" },
      { value: "AJUSTE", label: "Ajuste / diferença a maior" }, { value: "GLOSA", label: "Glosa / devolução (reduz)" }] },
    { name: "competence", label: "Competência (AAAA-MM)", required: true },
    { name: "amount", label: "Valor (R$)", type: "money", required: true },
    { name: "date", label: direction === "RECEBER" ? "Data do crédito" : "Data do pagamento", type: "date", required: true },
    { name: "document", label: "Documento (aviso, extrato, OB)" },
  ];
  return (
    <FormDialog title={direction === "RECEBER" ? "Lançar recebimento" : "Lançar pagamento"} size="md" fields={fields} onClose={onClose}
      description="Só requerimentos deferidos (ou cessados, para acertos). O fluxo mensal de cada competência é lançado uma vez; diferenças entram como ajuste ou glosa."
      initial={{ kind: "MENSAL", competence: prevMonth(), date: today() }} submitLabel="Lançar"
      submit={async (body) => { await api(`comprev/movimentos?sentido=${direction}`, { method: "POST", body }); toast.success("Lançado."); onDone(); }} />
  );
}

function RevenueDialog({ items, onClose, onDone }: { items: Movement[]; onClose: () => void; onDone: () => void }) {
  const accounts = useAccounts();
  const plan = items[0]?.plan;
  const total = items.reduce((s, m) => s + (m.kind === "GLOSA" ? -1 : 1) * Number(m.amount), 0);
  const mixed = new Set(items.map((m) => m.plan)).size > 1 || new Set(items.map((m) => m.date)).size > 1;
  return (
    <FormDialog title="Levar ao Financeiro" size="md" onClose={onClose}
      description={mixed ? "Atenção: selecione lançamentos do mesmo plano e da mesma data de crédito." : `${items.length} lançamento(s), total ${formatCurrency(total.toFixed(2))}, crédito em ${formatDate(items[0]?.date)}. Vira UMA receita do tipo COMPREV no plano ${items[0]?.plan_code}.`}
      fields={[{ name: "account", label: "Conta de crédito (mesmo plano)", type: "select", wide: true,
        options: [{ value: "", label: "Sem conta (informar depois)" }, ...(accounts.data?.results ?? []).filter((a) => a.plan === plan).map((a) => ({ value: a.id, label: a.label }))] }]}
      submitLabel="Gerar receita"
      submit={async (body) => {
        const r = await api<{ valor: string }>("comprev/movimentos/receita?sentido=RECEBER", { method: "POST", body: { ...body, ids: items.map((m) => m.id) } });
        toast.success(`Receita de ${formatCurrency(r.valor)} lançada no Financeiro.`);
        onDone();
      }} />
  );
}

// ============================================================ Fluxo mensal
export function ComprevFlowPage() {
  return <RequirePermission module="comprev.fluxo"><FlowScreen /></RequirePermission>;
}

function FlowScreen() {
  const { can } = useSession();
  const [comp, setComp] = useState(prevMonth());
  const { data, error, mutate } = useSWR<Flow>(comp ? `comprev/fluxo?competencia=${comp}` : null, fetcher);
  const [batch, setBatch] = useState<Dir | null>(null);
  return (
    <>
      <PageHeader title="Fluxo Mensal COMPREV" description="Por competência: quanto era previsto (valor mensal deferido) e quanto entrou ou saiu de fato. Diferenças mostram o que conferir com o COMPREV."
        breadcrumb={[{ label: "COMPREV" }, { label: "Fluxo Mensal" }]}
        actions={<label className="flex items-center gap-2 text-xs">Competência <Input type="month" className="h-8 w-40" value={comp} onChange={(e) => setComp(e.target.value)} /></label>} />
      {error && <ErrorState error={error} />}
      {data && (
        <>
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            {(["RECEBER", "PAGAR"] as Dir[]).map((d) => {
              const t = data.totais[d];
              return (
                <Card key={d}><CardContent className="space-y-1 p-4 text-xs">
                  <div className="flex items-center gap-1.5 font-semibold text-primary-strong">{d === "RECEBER" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}{d === "RECEBER" ? "A receber" : "A pagar"}</div>
                  <div className="text-lg font-semibold tabular">{formatCurrency(t.realizado)}</div>
                  <div className="text-muted-foreground">previsto {formatCurrency(t.previsto)}{t.atrasados ? ` · atrasados ${formatCurrency(t.atrasados)}` : ""}</div>
                  {t.pendentes > 0 && <div className="text-warning">{t.pendentes} requerimento(s) sem lançamento no mês</div>}
                </CardContent></Card>
              );
            })}
            <Card><CardContent className="space-y-1 p-4 text-xs">
              <div className="font-semibold text-primary-strong">Saldo do mês</div>
              <div className={cn("text-lg font-semibold tabular", Number(data.saldo) < 0 ? "text-critical" : "text-success")}>{formatCurrency(data.saldo)}</div>
              <div className="text-muted-foreground">recebido − pago (fluxo, ajustes e glosas; sem atrasados)</div>
            </CardContent></Card>
          </div>
          {(["RECEBER", "PAGAR"] as Dir[]).map((d) => {
            const rows = data.linhas.filter((r) => r.direction === d);
            const mod = d === "RECEBER" ? "comprev.recebimentos" : "comprev.pagamentos";
            const pend = rows.filter((r) => !r.registered && Number(r.expected) > 0);
            return (
              <Card key={d} className="mb-4">
                <CardHeader><CardTitle>{d === "RECEBER" ? "A receber" : "A pagar"} — {compLabel(data.competencia)}</CardTitle>
                  {pend.length > 0 && can(mod, "incluir") && <Button size="sm" onClick={() => setBatch(d)}><ListChecks /> Registrar o mês ({pend.length})</Button>}
                </CardHeader>
                <Table>
                  <TableHeader><TableRow><TableHead>Segurado / instituidor</TableHead><TableHead>Outro regime</TableHead><TableHead>Plano</TableHead><TableHead className="text-right">Previsto</TableHead><TableHead className="text-right">Realizado</TableHead><TableHead className="text-right">Diferença</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {rows.map((r) => (
                      <TableRow key={r.process}>
                        <TableCell className="font-medium">{r.person}</TableCell><TableCell className="text-xs">{r.counterpart}</TableCell><TableCell>{r.plan}</TableCell>
                        <TableCell className="text-right tabular">{formatCurrency(r.expected)}</TableCell>
                        <TableCell className="text-right tabular">{formatCurrency(r.realized)}</TableCell>
                        <TableCell className={cn("text-right tabular", Number(r.difference) < 0 ? "text-critical" : Number(r.difference) > 0 ? "text-success" : "")}>{formatCurrency(r.difference)}</TableCell>
                        <TableCell>{r.registered ? <Badge variant="success">Registrado</Badge> : Number(r.expected) > 0 ? <Badge variant="warning">Pendente</Badge> : <Badge variant="neutral">Acerto</Badge>}</TableCell>
                      </TableRow>
                    ))}
                    {rows.length === 0 && <EmptyRow cols={7} text="Nenhum requerimento compensando nesta competência." />}
                  </TableBody>
                </Table>
              </Card>
            );
          })}
        </>
      )}
      {batch && data && <BatchDialog direction={batch} comp={comp} rows={data.linhas.filter((r) => r.direction === batch && !r.registered && Number(r.expected) > 0)}
        onClose={() => setBatch(null)} onDone={() => mutate()} />}
    </>
  );
}

function BatchDialog({ direction, comp, rows, onClose, onDone }: { direction: Dir; comp: string; rows: FlowRow[]; onClose: () => void; onDone: () => void }) {
  const [amounts, setAmounts] = useState<Record<string, string>>(() => Object.fromEntries(rows.map((r) => [r.process, toBR(r.expected)])));
  const [on, setOn] = useState<Set<string>>(() => new Set(rows.map((r) => r.process)));
  const [date, setDate] = useState(today());
  const [doc, setDoc] = useState("");
  const [busy, setBusy] = useState(false);
  const total = useMemo(() => rows.filter((r) => on.has(r.process)).reduce((s, r) => s + Number(money(amounts[r.process] || "0")), 0), [rows, on, amounts]);
  const save = async () => {
    setBusy(true);
    try {
      const items = rows.filter((r) => on.has(r.process)).map((r) => ({ process: r.process, amount: money(amounts[r.process] || "") }));
      const r = await api<{ lancados: number }>(`comprev/movimentos/lote?sentido=${direction}`, { method: "POST", body: { competence: comp, date, document: doc, items } });
      toast.success(`${r.lancados} lançamento(s) registrados.`);
      onDone();
      onClose();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Registrar {direction === "RECEBER" ? "recebimentos" : "pagamentos"} de {compLabel(comp)}</DialogTitle>
          <DialogDescription>Confira cada valor com o demonstrativo do COMPREV. Desmarque quem não veio no mês; ajuste o valor se for diferente.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label={direction === "RECEBER" ? "Data do crédito" : "Data do pagamento"} required><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></FormField>
            <FormField label="Documento (aviso, extrato)"><Input value={doc} onChange={(e) => setDoc(e.target.value)} /></FormField>
          </div>
          <Table>
            <TableHeader><TableRow><TableHead className="w-8" /><TableHead>Segurado / instituidor</TableHead><TableHead className="text-right">Previsto</TableHead><TableHead className="w-40 text-right">Valor</TableHead></TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.process}>
                <TableCell><input type="checkbox" checked={on.has(r.process)} aria-label="Incluir" onChange={() => setOn((s) => { const n = new Set(s); if (n.has(r.process)) n.delete(r.process); else n.add(r.process); return n; })} /></TableCell>
                <TableCell>{r.person}</TableCell><TableCell className="text-right tabular">{formatCurrency(r.expected)}</TableCell>
                <TableCell><Input className="h-8 text-right" inputMode="decimal" disabled={!on.has(r.process)} value={amounts[r.process] ?? ""} onChange={(e) => setAmounts((a) => ({ ...a, [r.process]: e.target.value }))} /></TableCell>
              </TableRow>))}</TableBody>
          </Table>
          <div className="text-right text-sm">Total: <b className="tabular">{formatCurrency(total.toFixed(2))}</b></div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} disabled={busy || on.size === 0}>{busy && <Loader2 className="animate-spin" />} Registrar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================ Indicadores
type Indicators = {
  por_situacao: Record<Dir, Record<string, number>>; fluxo_mensal_vigente: Record<Dir, string>;
  ultimos_12_meses: { competencia: string; recebido: string; pago: string; saldo: string }[];
  atrasados: Record<Dir, { deferido: string; realizado: string; saldo: string }>;
  exigencias_vencidas: number; exigencias_15_dias: number; tempo_medio_deferimento: number | null; potencial: number;
  competencia_anterior: { competencia: string; pendentes: Record<Dir, number> };
};

export function ComprevIndicatorsPage() {
  return <RequirePermission module="comprev.indicadores"><IndicatorsScreen /></RequirePermission>;
}

function Kpi({ label, value, hint, tone }: { label: string; value: React.ReactNode; hint?: string; tone?: "warning" | "critical" | "success" }) {
  return (
    <Card><CardContent className="space-y-0.5 p-4">
      <div className="text-2xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("text-xl font-semibold tabular", tone === "warning" && "text-warning", tone === "critical" && "text-critical", tone === "success" && "text-success")}>{value}</div>
      {hint && <div className="text-2xs text-muted-foreground">{hint}</div>}
    </CardContent></Card>
  );
}

function IndicatorsScreen() {
  const { data, error } = useSWR<Indicators>("comprev/indicadores", fetcher);
  const max = Math.max(1, ...(data?.ultimos_12_meses ?? []).flatMap((m) => [Number(m.recebido), Number(m.pago)]));
  const count = (d: Dir, ...s: string[]) => s.reduce((n, k) => n + (data?.por_situacao[d][k] ?? 0), 0);
  return (
    <>
      <PageHeader title="Indicadores COMPREV" description="Visão geral da compensação: quanto entra e sai por mês, requerimentos por situação, atrasados e pendências."
        breadcrumb={[{ label: "COMPREV" }, { label: "Indicadores" }]} />
      {error && <ErrorState error={error} />}
      {data && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="Fluxo mensal a receber" value={formatCurrency(data.fluxo_mensal_vigente.RECEBER)} hint={`${count("RECEBER", "DEFERIDO")} requerimento(s) deferido(s)`} tone="success" />
            <Kpi label="Fluxo mensal a pagar" value={formatCurrency(data.fluxo_mensal_vigente.PAGAR)} hint={`${count("PAGAR", "DEFERIDO")} requerimento(s) deferido(s)`} />
            <Kpi label="Atrasados a receber" value={formatCurrency(data.atrasados.RECEBER.saldo)} hint={`deferido ${formatCurrency(data.atrasados.RECEBER.deferido)} · recebido ${formatCurrency(data.atrasados.RECEBER.realizado)}`} />
            <Kpi label="Em análise no COMPREV" value={count("RECEBER", "ENVIADO", "EXIGENCIA") + count("PAGAR", "ENVIADO", "EXIGENCIA")}
              hint={data.tempo_medio_deferimento != null ? `tempo médio até o deferimento: ${data.tempo_medio_deferimento} dias` : "sem deferimentos ainda"} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="Exigências vencidas" value={data.exigencias_vencidas} tone={data.exigencias_vencidas ? "critical" : undefined} />
            <Kpi label="Exigências vencendo em 15 dias" value={data.exigencias_15_dias} tone={data.exigencias_15_dias ? "warning" : undefined} />
            <Kpi label="Benefícios sem requerimento" value={data.potencial} hint="com tempo averbado de outro regime" tone={data.potencial ? "warning" : undefined} />
            <Kpi label={`Sem lançamento em ${compLabel(data.competencia_anterior.competencia)}`} value={data.competencia_anterior.pendentes.RECEBER + data.competencia_anterior.pendentes.PAGAR}
              hint={`${data.competencia_anterior.pendentes.RECEBER} a receber · ${data.competencia_anterior.pendentes.PAGAR} a pagar`} />
          </div>
          <Card>
            <CardHeader><CardTitle>Últimos 12 meses — recebido × pago</CardTitle>
              <div className="flex gap-3 text-2xs"><span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-success" />Recebido</span><span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-warning" />Pago</span></div>
            </CardHeader>
            <CardContent>
              <div className="flex h-44 items-end gap-2">
                {data.ultimos_12_meses.map((m) => (
                  <div key={m.competencia} className="flex flex-1 flex-col items-center gap-1" title={`${compLabel(m.competencia)}: recebido ${formatCurrency(m.recebido)} · pago ${formatCurrency(m.pago)} · saldo ${formatCurrency(m.saldo)}`}>
                    <div className="flex h-36 w-full items-end justify-center gap-0.5">
                      <div className="w-1/2 max-w-4 rounded-t bg-success" style={{ height: `${(100 * Math.max(0, Number(m.recebido))) / max}%` }} />
                      <div className="w-1/2 max-w-4 rounded-t bg-warning" style={{ height: `${(100 * Math.max(0, Number(m.pago))) / max}%` }} />
                    </div>
                    <div className="text-[10px] text-muted-foreground">{compLabel(m.competencia).slice(0, 2)}/{m.competencia.slice(2, 4)}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Requerimentos por situação</CardTitle></CardHeader>
            <Table>
              <TableHeader><TableRow><TableHead>Situação</TableHead><TableHead className="text-right">A receber</TableHead><TableHead className="text-right">A pagar</TableHead></TableRow></TableHeader>
              <TableBody>{STATUS.map(([s, l]) => (
                <TableRow key={s}><TableCell><Badge variant={VARIANT[s]}>{l}</Badge></TableCell>
                  <TableCell className="text-right tabular">{data.por_situacao.RECEBER[s] ?? 0}</TableCell><TableCell className="text-right tabular">{data.por_situacao.PAGAR[s] ?? 0}</TableCell></TableRow>
              ))}</TableBody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
