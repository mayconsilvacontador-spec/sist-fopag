"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Pencil, Plus, Search } from "lucide-react";

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
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox, Input, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { BenefitRow, PayrollEntryFixed, PersonRow, Rubric } from "@/lib/types";

import { BenefitPicker } from "./benefit-picker";

export type EntryKind = "MANUAL" | "CONSIGNACAO" | "PENSAO_ALIMENTICIA";

const CFG: Record<EntryKind, { module: string; endpoint: string; title: string; description: string; singular: string }> = {
  MANUAL: {
    module: "folha.diferencas", endpoint: "folha/diferencas", title: "Diferenças e lançamentos", singular: "lançamento",
    description: "Valores informados por benefício: diferenças de proventos, reposições ao erário, descontos judiciais. Valem a partir da competência inicial, por prazo ou parcelas.",
  },
  CONSIGNACAO: {
    module: "folha.consignacoes", endpoint: "folha/consignacoes", title: "Consignações", singular: "consignação",
    description: "Empréstimos, cartões e mensalidades. Descontados só dentro da margem consignável (parâmetro folha.margem_consignavel); o que não couber gera aviso na folha.",
  },
  PENSAO_ALIMENTICIA: {
    module: "folha.pensao_alimenticia", endpoint: "folha/pensoes-alimenticias", title: "Pensão alimentícia", singular: "pensão alimentícia",
    description: "Descontos por decisão judicial ou acordo homologado. Percentual sobre o bruto ou o líquido (bruto − contribuição − IRRF), ou valor fixo. Dedutível do IRRF.",
  },
};

const comp = (d: string | null) => (d ? `${d.slice(5, 7)}/${d.slice(0, 4)}` : "—");
const pct = (v: string | null) => (v ? `${Number(v).toLocaleString("pt-BR")}%` : "");

export function EntriesPage({ kind }: { kind: EntryKind }) {
  return (
    <RequirePermission module={CFG[kind].module}>
      <Entries kind={kind} />
    </RequirePermission>
  );
}

function Entries({ kind }: { kind: EntryKind }) {
  const cfg = CFG[kind];
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [onlyActive, setOnlyActive] = useState(true);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<PayrollEntryFixed | "new" | null>(null);
  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const { data, error, isLoading, mutate } = useSWR<Paginated<PayrollEntryFixed>>(
    `${cfg.endpoint}${qs({ search: debounced, ativos: onlyActive ? 1 : undefined, page })}`, fetcher, { keepPreviousData: true });

  return (
    <>
      <PageHeader title={cfg.title} description={cfg.description} breadcrumb={[{ label: "Folha de Benefícios" }, { label: cfg.title }]}
        actions={can(cfg.module, "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Novo</Button>} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Beneficiário, CPF ou contrato/processo" className="pl-8" />
          </div>
          <label className="flex items-center gap-2 text-xs"><Checkbox checked={onlyActive} onChange={(e) => { setOnlyActive(e.target.checked); setPage(1); }} /> Somente ativos</label>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Beneficiário</TableHead><TableHead>Rubrica</TableHead>
            {kind === "CONSIGNACAO" && <TableHead>Consignatária</TableHead>}
            {kind === "PENSAO_ALIMENTICIA" && <TableHead>Alimentando</TableHead>}
            <TableHead className="text-right">Valor</TableHead><TableHead>Período</TableHead><TableHead>Parcelas</TableHead><TableHead>Situação</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={8} />}
            {data?.results.map((e) => (
              <TableRow key={e.id}>
                <TableCell><div className="font-medium">{e.beneficiary_name}</div><div className="text-2xs text-muted-foreground">{e.beneficiary_cpf} · {e.folha}</div></TableCell>
                <TableCell className="text-xs"><span className="font-mono">{e.rubric_code}</span> {e.rubric_name}{e.description ? ` — ${e.description}` : ""}{e.contract && <div className="text-2xs text-muted-foreground">{e.contract}</div>}</TableCell>
                {kind === "CONSIGNACAO" && <TableCell className="text-xs">{e.consignee_name}</TableCell>}
                {kind === "PENSAO_ALIMENTICIA" && <TableCell className="text-xs">{e.alimony_beneficiary_name || "—"}</TableCell>}
                <TableCell className="text-right tabular">{e.amount ? formatCurrency(e.amount) : `${pct(e.percent)}${e.base ? ` do ${e.base === "LIQUIDO" ? "líquido" : "bruto"}` : ""}`}</TableCell>
                <TableCell className="text-xs">{comp(e.start)} a {e.end ? comp(e.end) : "indeterminado"}</TableCell>
                <TableCell className="text-xs">{e.installments ? `${e.paid_installments}/${e.installments}` : "—"}</TableCell>
                <TableCell>{e.active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}</TableCell>
                <TableCell>{can(cfg.module, "editar") && <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(e)} aria-label="Editar"><Pencil /></Button>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={8} />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {editing && <EntryDialog kind={kind} row={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => mutate()} />}
    </>
  );
}

function EntryDialog({ kind, row, onClose, onSaved }: { kind: EntryKind; row: PayrollEntryFixed | null; onClose: () => void; onSaved: () => void }) {
  const cfg = CFG[kind];
  const rubrics = useSWR<Paginated<Rubric>>(`folha/rubricas${qs({ calc: kind, vigentes: 1, ativos: 1, page_size: 100 })}`, fetcher);
  const consignees = useSWR<Paginated<{ id: string; name: string }>>(kind === "CONSIGNACAO" ? "folha/consignatarias?ativos=1&page_size=500" : null, fetcher);
  const [benefit, setBenefit] = useState<BenefitRow | null>(null);
  const [alimentando, setAlimentando] = useState<PersonRow | null>(null);
  const [mode, setMode] = useState<"amount" | "percent">(row?.percent ? "percent" : "amount");
  const [f, setF] = useState(() => ({
    rubric_code: row?.rubric_code ?? "", description: row?.description ?? "", amount: row?.amount?.replace(".", ",") ?? "",
    percent: row?.percent ?? "", base: row?.base || "BRUTO", start: row?.start?.slice(0, 7) ?? new Date().toISOString().slice(0, 7),
    end: row?.end?.slice(0, 7) ?? "", installments: row?.installments ? String(row.installments) : "", consignee: row?.consignee ?? "",
    contract: row?.contract ?? "", on_13: row?.on_13 ?? true, active: row?.active ?? true, notes: row?.notes ?? "",
  }));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string | boolean) => setF((s) => ({ ...s, [k]: v }));

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!row && !benefit) { toast.error("Escolha o benefício."); return; }
    setBusy(true);
    setErrors({});
    const money = (v: string) => (v.includes(",") ? v.replace(/\./g, "").replace(",", ".") : v);
    const body: Record<string, unknown> = {
      rubric_code: f.rubric_code, description: f.description, contract: f.contract, notes: f.notes, active: f.active,
      amount: mode === "amount" && f.amount ? money(f.amount) : null,
      percent: mode === "percent" && f.percent ? money(String(f.percent)) : null,
      base: mode === "percent" && kind === "PENSAO_ALIMENTICIA" ? f.base : "",
      start: `${f.start}-01`, end: f.end ? `${f.end}-01` : null,
      installments: f.installments ? Number(f.installments) : null,
      consignee: kind === "CONSIGNACAO" ? f.consignee || null : null,
      on_13: f.on_13,
    };
    if (!row) body.benefit = benefit!.id;
    if (kind === "PENSAO_ALIMENTICIA" && alimentando) body.alimony_beneficiary = alimentando.id;
    try {
      if (row) await api(`${cfg.endpoint}/${row.id}`, { method: "PATCH", body });
      else await api(cfg.endpoint, { method: "POST", body });
      toast.success("Salvo. Vale a partir do próximo cálculo da folha.");
      onSaved();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="md">
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader>
            <DialogTitle>{row ? `Editar ${cfg.singular}` : `Novo(a) ${cfg.singular}`}</DialogTitle>
            <DialogDescription>Não há exclusão: para encerrar, informe a competência final ou inative.</DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <div className="mb-1 text-xs font-medium text-foreground/80">Benefício</div>
              {row ? <div className="rounded-md border bg-muted/40 px-3 py-2 text-xs">{row.beneficiary_name} · {row.folha}</div>
                : <BenefitPicker value={benefit} onChange={setBenefit} />}
            </div>
            <FormField label="Rubrica" htmlFor="e-rub" required error={errors.rubric_code} className="sm:col-span-2">
              <Select id="e-rub" value={f.rubric_code} onChange={(e) => set("rubric_code", e.target.value)} required>
                <option value="">Selecione</option>
                {rubrics.data?.results.map((r) => <option key={r.id} value={r.code}>{r.code} — {r.name} ({r.kind_display.toLowerCase()})</option>)}
              </Select>
            </FormField>
            {kind === "CONSIGNACAO" && (
              <FormField label="Consignatária" htmlFor="e-cons" required error={errors.consignee} className="sm:col-span-2" hint="Cadastre em Folha › Consignatárias.">
                <Select id="e-cons" value={f.consignee} onChange={(e) => set("consignee", e.target.value)} required>
                  <option value="">Selecione</option>
                  {consignees.data?.results.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
              </FormField>
            )}
            {kind === "PENSAO_ALIMENTICIA" && (
              <div className="sm:col-span-2">
                <div className="mb-1 text-xs font-medium text-foreground/80">Alimentando (quem recebe)</div>
                {row?.alimony_beneficiary_name && !alimentando ? <div className="text-xs">{row.alimony_beneficiary_name}</div>
                  : <PersonPicker value={alimentando} onChange={setAlimentando} />}
              </div>
            )}
            <FormField label={kind === "PENSAO_ALIMENTICIA" ? "Processo judicial / acordo" : "Contrato / processo"} htmlFor="e-contract"
              required={kind === "PENSAO_ALIMENTICIA"} error={errors.contract}>
              <Input id="e-contract" value={f.contract} onChange={(e) => set("contract", e.target.value)} maxLength={60} />
            </FormField>
            <FormField label="Descrição complementar" htmlFor="e-desc" error={errors.description}>
              <Input id="e-desc" value={f.description} onChange={(e) => set("description", e.target.value)} maxLength={120} />
            </FormField>
            <FormField label="Forma" htmlFor="e-mode">
              <Select id="e-mode" value={mode} onChange={(e) => setMode(e.target.value as "amount" | "percent")}>
                <option value="amount">Valor fixo (R$)</option><option value="percent">Percentual</option>
              </Select>
            </FormField>
            {mode === "amount" ? (
              <FormField label="Valor (R$)" htmlFor="e-amount" required error={errors.amount}>
                <Input id="e-amount" inputMode="decimal" placeholder="0,00" value={f.amount} onChange={(e) => set("amount", e.target.value)} required />
              </FormField>
            ) : (
              <FormField label={kind === "PENSAO_ALIMENTICIA" ? "Percentual" : "Percentual do benefício"} htmlFor="e-pct" required error={errors.percent}>
                <Input id="e-pct" inputMode="decimal" value={f.percent} onChange={(e) => set("percent", e.target.value)} required />
              </FormField>
            )}
            {kind === "PENSAO_ALIMENTICIA" && mode === "percent" && (
              <FormField label="Base do percentual" htmlFor="e-base">
                <Select id="e-base" value={f.base} onChange={(e) => set("base", e.target.value)}>
                  <option value="BRUTO">Rendimento bruto</option><option value="LIQUIDO">Líquido (bruto − contribuição − IRRF)</option>
                </Select>
              </FormField>
            )}
            <FormField label="Competência inicial" htmlFor="e-start" required error={errors.start}>
              <Input id="e-start" type="month" value={f.start} onChange={(e) => set("start", e.target.value)} required />
            </FormField>
            <FormField label="Competência final" htmlFor="e-end" hint="Vazio = indeterminado" error={errors.end}>
              <Input id="e-end" type="month" value={f.end} onChange={(e) => set("end", e.target.value)} />
            </FormField>
            {kind !== "PENSAO_ALIMENTICIA" && (
              <FormField label="Nº de parcelas" htmlFor="e-inst" hint="Avança a cada folha fechada" error={errors.installments}>
                <Input id="e-inst" type="number" min={1} value={f.installments} onChange={(e) => set("installments", e.target.value)} />
              </FormField>
            )}
            {kind === "PENSAO_ALIMENTICIA" && (
              <label className="flex items-center gap-2 self-end pb-2 text-xs"><Checkbox checked={f.on_13} onChange={(e) => set("on_13", e.target.checked)} /> Incide também sobre o 13º</label>
            )}
            <FormField label="Observações" htmlFor="e-notes" className="sm:col-span-2">
              <Textarea id="e-notes" value={f.notes} onChange={(e) => set("notes", e.target.value)} />
            </FormField>
            {row && <label className="flex items-center gap-2 text-xs sm:col-span-2"><Checkbox checked={f.active} onChange={(e) => set("active", e.target.checked)} /> Ativo</label>}
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
