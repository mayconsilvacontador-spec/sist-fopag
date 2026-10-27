"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CheckCircle2, Download, FileUp, Link2, Loader2, Plus, Wand2, XCircle } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog, RegistryPage } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, download, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import type { PayrollRun } from "@/lib/types";

import { compLabel, useAccounts, usePlans } from "./common";

const crumbs = (t: string) => [{ label: "Gestão Financeira" }, { label: t }];

async function upload(path: string, fields: Record<string, string>, file: File) {
  const fd = new FormData();
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
  fd.append("file", file);
  const res = await fetch(`/api/backend/${path}`, { method: "POST", body: fd, credentials: "same-origin" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || Object.values(body).flat().join(" ") || "Falha no envio do arquivo.");
  return body;
}

// ------------------------------------------------------------------ Contas (bancos)
export function AccountsPage() {
  return (
    <RegistryPage config={{
      module: "financeiro.bancos", endpoint: "financeiro/contas", title: "Contas bancárias da instituição", singular: "Conta",
      breadcrumb: "Gestão Financeira",
      description: "Uma ou mais contas por plano. Pagamentos e receitas só usam conta do MESMO plano (segregação de massas). Os dados do convênio são usados no arquivo CNAB 240.",
      searchPlaceholder: "Conta",
      columns: [
        { label: "Plano", render: (r) => <Badge variant="info">{String(r.plan_code)}</Badge> },
        { label: "Banco", render: (r) => String(r.bank_label) },
        { label: "Agência / conta", render: (r) => <span className="font-mono text-xs">{`${r.branch}${r.branch_digit ? "-" + r.branch_digit : ""} / ${r.account}${r.account_digit ? "-" + r.account_digit : ""}`}</span> },
        { label: "Finalidade", render: (r) => String(r.purpose_display) },
        { label: "Convênio", render: (r) => String(r.agreement || "—") },
      ],
      fields: [
        { name: "plan", label: "Plano", type: "ref", required: true, ref: { endpoint: "plans", label: (r) => `${r.code} — ${r.name}` } },
        { name: "bank", label: "Banco", type: "ref", required: true, ref: { endpoint: "banks", label: (r) => `${r.code} - ${r.name}` } },
        { name: "branch", label: "Agência", type: "digits", maxLength: 5, required: true },
        { name: "branch_digit", label: "Dígito da agência", maxLength: 1 },
        { name: "account", label: "Conta", type: "digits", maxLength: 12, required: true },
        { name: "account_digit", label: "Dígito da conta", maxLength: 2 },
        { name: "purpose", label: "Finalidade", type: "select", required: true, options: [
          { value: "PAGAMENTO", label: "Pagamento de benefícios" }, { value: "ARRECADACAO", label: "Arrecadação" },
          { value: "APLICACAO", label: "Aplicação financeira" }, { value: "OUTROS", label: "Outros" }] },
        { name: "description", label: "Descrição" },
        { name: "agreement", label: "Código do convênio (CNAB)", hint: "Fornecido pelo banco" },
        { name: "cnab_service", label: "Tipo de serviço CNAB", maxLength: 2, hint: "30 = salários/benefícios" },
        { name: "cnab_file_version", label: "Versão do arquivo", maxLength: 3 },
        { name: "cnab_batch_version", label: "Versão do lote", maxLength: 3 },
      ],
      defaults: { purpose: "PAGAMENTO", cnab_service: "30", cnab_file_version: "089", cnab_batch_version: "045" },
    }} />
  );
}

// ------------------------------------------------------------------ Pagamentos
type Batch = {
  id: string; number: number; status: string; status_display: string; plan_code: string; account: string; account_label: string;
  run_label: string; payroll_run: string; payment_date: string; total: string; items_count: number; approved_by_name: string;
  approved_at: string | null; notes: string; counts: Record<string, number>;
};
type Item = { id: string; beneficiary_name: string; our_number: string; bank: Record<string, string>; amount: string; status: string; status_display: string; return_message: string };
const BATCH_VARIANT: Record<string, "neutral" | "info" | "warning" | "success" | "critical"> = {
  RASCUNHO: "neutral", APROVADO: "info", ARQUIVO_GERADO: "warning", PROCESSADO: "success", CANCELADO: "critical",
};

export function PaymentsPage() {
  return <RequirePermission module="financeiro.pagamentos"><Payments /></RequirePermission>;
}

function Payments() {
  const { can } = useSession();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Batch>>(`financeiro/lotes${qs({ page })}`, fetcher);
  const runs = useSWR<Paginated<PayrollRun>>(creating ? "folha/folhas?situacoes=FECHADA&page_size=50" : null, fetcher);
  const accounts = useAccounts();
  return (
    <>
      <PageHeader title="Pagamentos" breadcrumb={crumbs("Pagamentos")}
        description="Lote de pagamento da folha fechada → aprovação → arquivo CNAB 240 → retorno do banco. Quando todos os líquidos forem pagos, a folha passa a PAGA automaticamente."
        actions={can("financeiro.pagamentos", "incluir") && <Button onClick={() => setCreating(true)}><Plus /> Novo lote</Button>} />
      {error && <ErrorState error={error} />}
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Lote</TableHead><TableHead>Folha</TableHead><TableHead>Conta pagadora</TableHead><TableHead>Crédito em</TableHead><TableHead className="text-right">Qtde.</TableHead><TableHead className="text-right">Total</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={7} />}
            {data?.results.map((b) => (
              <TableRow key={b.id} className="cursor-pointer" onClick={() => setOpen(b.id)}>
                <TableCell className="font-semibold text-primary">{b.number}</TableCell>
                <TableCell className="text-xs">{b.run_label}</TableCell>
                <TableCell className="text-xs">{b.account_label}</TableCell>
                <TableCell>{formatDate(b.payment_date)}</TableCell>
                <TableCell className="text-right tabular">{b.items_count}</TableCell>
                <TableCell className="text-right tabular">{formatCurrency(b.total)}</TableCell>
                <TableCell><Badge variant={BATCH_VARIANT[b.status]}>{b.status_display}</Badge>
                  {b.counts.REJEITADO ? <Badge variant="critical" className="ml-1">{b.counts.REJEITADO} rejeitado(s)</Badge> : null}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={7} text="Nenhum lote." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {creating && (
        <FormDialog title="Novo lote de pagamento" size="md" onClose={() => setCreating(false)}
          description="Inclui os líquidos da folha que ainda não estão em lote (os rejeitados pelo banco voltam no próximo lote). Beneficiários sem conta ficam de fora."
          fields={[
            { name: "run", label: "Folha fechada", type: "select", required: true, wide: true,
              options: (runs.data?.results ?? []).map((r) => ({ value: r.id, label: `${String(r.month).padStart(2, "0")}/${r.year} — ${r.folha} ${r.kind === "DECIMO" ? "(13º)" : ""}` })) },
            { name: "account", label: "Conta pagadora", type: "select", required: true, wide: true,
              options: (accounts.data?.results ?? []).map((a) => ({ value: a.id, label: `${a.label} — ${a.purpose_display}` })) },
            { name: "payment_date", label: "Data do crédito", type: "date", required: true },
          ]}
          submitLabel="Criar lote"
          submit={async (body) => {
            const b = await api<Batch>("financeiro/lotes", { method: "POST", body });
            toast.success(`Lote ${b.number} criado: ${b.items_count} pagamento(s), ${formatCurrency(b.total)}.`);
            mutate();
            setOpen(b.id);
          }} />
      )}
      {open && <BatchDialog id={open} onClose={() => setOpen(null)} onChanged={() => mutate()} />}
    </>
  );
}

function BatchDialog({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { can } = useSession();
  const { data: b, mutate } = useSWR<Batch>(`financeiro/lotes/${id}`, fetcher);
  const items = useSWR<Paginated<Item>>(`financeiro/lotes/${id}/items?page_size=500`, fetcher);
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState<"cancel" | "manual" | null>(null);
  const act = async (key: string, path: string, body?: Record<string, unknown>, ok?: string) => {
    setBusy(key);
    try {
      const r = await api<{ id: string; file_name?: string }>(`financeiro/lotes/${id}/${path}`, { method: "POST", body });
      toast.success(ok ?? "Feito.");
      if (path === "remittance" && r.file_name) await download(`financeiro/arquivos/${r.id}/download`, r.file_name);
      mutate();
      items.mutate();
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
      throw err;
    } finally {
      setBusy("");
    }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Lote {b?.number}</DialogTitle>
          {b && <DialogDescription>{b.run_label} · {b.account_label} · crédito em {formatDate(b.payment_date)} · <Badge variant={BATCH_VARIANT[b.status]}>{b.status_display}</Badge></DialogDescription>}
        </DialogHeader>
        <DialogBody className="space-y-3 text-xs">
          {b && <>
            <div className="flex flex-wrap gap-2">
              {b.status === "RASCUNHO" && can("financeiro.pagamentos", "aprovar") && (
                <Button size="sm" onClick={() => act("ap", "approve", undefined, "Lote aprovado.").catch(() => undefined)} disabled={!!busy}><CheckCircle2 /> Aprovar</Button>
              )}
              {b.status === "APROVADO" && can("financeiro.arquivos_bancarios", "incluir") && (
                <Button size="sm" onClick={() => act("rem", "remittance", undefined, "Arquivo CNAB 240 gerado.").catch(() => undefined)} disabled={!!busy}>
                  {busy === "rem" ? <Loader2 className="animate-spin" /> : <Download />} Gerar arquivo CNAB 240</Button>
              )}
              {b.status === "ARQUIVO_GERADO" && can("financeiro.pagamentos", "aprovar") && (
                <Button size="sm" variant="outline" onClick={() => setConfirm("manual")}><CheckCircle2 /> Confirmar pagamento sem retorno</Button>
              )}
              {["RASCUNHO", "APROVADO"].includes(b.status) && can("financeiro.pagamentos", "editar") && (
                <Button size="sm" variant="outline" onClick={() => setConfirm("cancel")}><XCircle /> Cancelar lote</Button>
              )}
            </div>
            {b.status === "ARQUIVO_GERADO" && <p className="text-muted-foreground">Envie o arquivo ao banco e importe o retorno em Gestão Financeira › Arquivos Bancários.</p>}
            {b.notes && <p className="text-warning">{b.notes}</p>}
            <Table>
              <TableHeader><TableRow><TableHead>Beneficiário</TableHead><TableHead>Conta</TableHead><TableHead className="text-right">Valor</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
              <TableBody>
                {!items.data && <LoadingRows cols={4} />}
                {items.data?.results.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell>{i.beneficiary_name}<div className="text-2xs text-muted-foreground">{i.our_number}</div></TableCell>
                    <TableCell className="font-mono text-2xs">{i.bank.banco} · {i.bank.agencia} · {i.bank.conta}{i.bank.conta_dv ? "-" + i.bank.conta_dv : ""}</TableCell>
                    <TableCell className="text-right tabular">{formatCurrency(i.amount)}</TableCell>
                    <TableCell><Badge variant={i.status === "PAGO" ? "success" : i.status === "REJEITADO" ? "critical" : "neutral"}>{i.status_display}</Badge>
                      {i.return_message && <div className="text-2xs text-muted-foreground">{i.return_message}</div>}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>}
        </DialogBody>
      </DialogContent>
      <ConfirmDialog open={confirm === "cancel"} onOpenChange={(v) => !v && setConfirm(null)} title="Cancelar o lote?" requireJustification destructive
        confirmLabel="Cancelar lote" onConfirm={(j) => act("can", "cancel", { justification: j }, "Lote cancelado.")} />
      <ConfirmDialog open={confirm === "manual"} onOpenChange={(v) => !v && setConfirm(null)} title="Confirmar pagamento sem arquivo de retorno?" requireJustification
        description="Use só quando o banco não fornecer retorno. Todos os itens enviados serão marcados como pagos. Fica registrado na auditoria."
        confirmLabel="Confirmar" onConfirm={(j) => act("man", "confirm", { justification: j }, "Pagamento confirmado.")} />
    </Dialog>
  );
}

// ------------------------------------------------------------------ Arquivos bancários
type BankFile = { id: string; kind: string; kind_display: string; account_label: string; batch_number: number | null; nsa: number | null; file_name: string; sha256: string; summary: Record<string, unknown>; user_name: string; created_at: string };

export function BankFilesPage() {
  return <RequirePermission module="financeiro.arquivos_bancarios"><BankFiles /></RequirePermission>;
}

function BankFiles() {
  const { can } = useSession();
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState("");
  const accounts = useAccounts();
  const [account, setAccount] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const { data, error, mutate } = useSWR<Paginated<BankFile>>(`financeiro/arquivos${qs({ page, kind })}`, fetcher);
  const send = async () => {
    if (!file || !account) { toast.error("Escolha a conta e o arquivo."); return; }
    setBusy(true);
    try {
      const r = await upload("financeiro/arquivos/import-return", { account }, file);
      toast.success(`Retorno processado: ${r.PAGO} pago(s), ${r.REJEITADO} rejeitado(s), ${r.AGENDADO} agendado(s).`);
      setFile(null);
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeader title="Arquivos Bancários" breadcrumb={crumbs("Arquivos Bancários")}
        description="Remessas CNAB 240 geradas, retornos do banco e extratos importados — todos guardados com hash SHA-256." />
      <Card className="mb-3 border-info/30 bg-info/5 px-4 py-2 text-xs">
        O arquivo segue o CNAB 240 genérico da FEBRABAN (crédito em conta e TED). Antes do uso em produção, <b>homologue o arquivo com o banco</b> (cada banco tem particularidades: versão, tipo de serviço, finalidade de TED) e ajuste os dados do convênio em Gestão Financeira › Bancos.
      </Card>
      {can("financeiro.arquivos_bancarios", "incluir") && (
        <Card className="mb-3 flex flex-wrap items-end gap-3 px-4 py-3">
          <FormField label="Conta" htmlFor="rf-acc" className="w-72">
            <Select id="rf-acc" value={account} onChange={(e) => setAccount(e.target.value)}>
              <option value="">Selecione</option>
              {accounts.data?.results.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
            </Select>
          </FormField>
          <FormField label="Arquivo de retorno (CNAB 240)" htmlFor="rf-file" className="min-w-64 flex-1">
            <Input id="rf-file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </FormField>
          <Button onClick={send} disabled={busy || !file}>{busy ? <Loader2 className="animate-spin" /> : <FileUp />} Importar retorno</Button>
        </Card>
      )}
      {error && <ErrorState error={error} />}
      <Card>
        <div className="border-b px-4 py-2.5">
          <Select className="w-48" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} aria-label="Tipo">
            <option value="">Todos os tipos</option><option value="REMESSA">Remessas</option><option value="RETORNO">Retornos</option><option value="EXTRATO">Extratos</option>
          </Select>
        </div>
        <Table>
          <TableHeader><TableRow><TableHead>Arquivo</TableHead><TableHead>Tipo</TableHead><TableHead>Conta</TableHead><TableHead>Resumo</TableHead><TableHead>Gerado em</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={6} />}
            {data?.results.map((f) => (
              <TableRow key={f.id}>
                <TableCell className="font-mono text-xs">{f.file_name}<div className="text-2xs text-muted-foreground" title={f.sha256}>SHA-256 {f.sha256.slice(0, 16)}…</div></TableCell>
                <TableCell>{f.kind_display}{f.batch_number ? ` · lote ${f.batch_number}` : ""}</TableCell>
                <TableCell className="text-xs">{f.account_label}</TableCell>
                <TableCell className="text-2xs">{Object.entries(f.summary).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k}: ${v}`).join(" · ")}</TableCell>
                <TableCell className="text-xs">{formatDateTime(f.created_at)}<div className="text-2xs text-muted-foreground">{f.user_name}</div></TableCell>
                <TableCell>{can("financeiro.arquivos_bancarios", "exportar") && (
                  <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Baixar" onClick={() => download(`financeiro/arquivos/${f.id}/download`, f.file_name).catch((e) => toast.error((e as Error).message))}><Download /></Button>)}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum arquivo." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
    </>
  );
}

// ------------------------------------------------------------------ Conciliação bancária
type Line = { id: string; date: string; amount: string; fitid: string; memo: string; reconciled: boolean; revenue: string | null; revenue_label: string; batch: string | null; batch_number: number | null; note: string };
type RevenueRow = { id: string; date: string; amount: string; description: string; kind_display: string };

export function BankReconciliationPage() {
  return <RequirePermission module="financeiro.conciliacao"><BankRec /></RequirePermission>;
}

function BankRec() {
  const { can } = useSession();
  const accounts = useAccounts();
  const [account, setAccount] = useState("");
  const [pending, setPending] = useState(true);
  const [page, setPage] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [matching, setMatching] = useState<Line | null>(null);
  const { data, mutate } = useSWR<Paginated<Line>>(account ? `financeiro/extrato${qs({ account, reconciled: pending ? "false" : undefined, page })}` : null, fetcher);
  const send = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const r = await upload("financeiro/extrato/import", { account }, file);
      toast.success(`${r.lancamentos} lançamento(s) importado(s) (${r.repetidos} repetido(s)); ${r.conciliados_automaticamente} conciliado(s) automaticamente.`);
      setFile(null);
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const auto = async () => {
    try {
      const r = await api<{ conciliados: number }>("financeiro/extrato/auto", { method: "POST", body: { account } });
      toast.success(`${r.conciliados} lançamento(s) conciliado(s).`);
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };
  return (
    <>
      <PageHeader title="Conciliação Bancária" breadcrumb={crumbs("Conciliação Bancária")}
        description="Importe o extrato OFX da conta. Créditos são conciliados com as receitas (mesmo valor, data ±3 dias) e débitos com os lotes de pagamento; o restante é conciliado manualmente." />
      <Card className="mb-3 flex flex-wrap items-end gap-3 px-4 py-3">
        <FormField label="Conta" htmlFor="br-acc" className="w-72">
          <Select id="br-acc" value={account} onChange={(e) => { setAccount(e.target.value); setPage(1); }}>
            <option value="">Selecione</option>
            {accounts.data?.results.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </Select>
        </FormField>
        {account && can("financeiro.conciliacao", "editar") && <>
          <FormField label="Extrato (OFX)" htmlFor="br-file" className="min-w-56 flex-1">
            <Input id="br-file" type="file" accept=".ofx,.OFX" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </FormField>
          <Button onClick={send} disabled={busy || !file}>{busy ? <Loader2 className="animate-spin" /> : <FileUp />} Importar extrato</Button>
          <Button variant="outline" onClick={auto}><Wand2 /> Conciliar automaticamente</Button>
        </>}
      </Card>
      {account && (
        <Card>
          <div className="border-b px-4 py-2.5">
            <Select className="w-56" value={pending ? "1" : "0"} onChange={(e) => { setPending(e.target.value === "1"); setPage(1); }} aria-label="Filtro">
              <option value="1">Somente não conciliados</option><option value="0">Todos os lançamentos</option>
            </Select>
          </div>
          <Table>
            <TableHeader><TableRow><TableHead>Data</TableHead><TableHead>Histórico</TableHead><TableHead className="text-right">Valor</TableHead><TableHead>Conciliação</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {!data && <LoadingRows cols={5} />}
              {data?.results.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>{formatDate(l.date)}</TableCell>
                  <TableCell className="text-xs">{l.memo}<div className="text-2xs text-muted-foreground">{l.fitid}</div></TableCell>
                  <TableCell className={`text-right tabular ${Number(l.amount) < 0 ? "text-critical" : "text-success"}`}>{formatCurrency(l.amount)}</TableCell>
                  <TableCell className="text-xs">{l.reconciled ? (l.revenue_label || (l.batch_number ? `Lote ${l.batch_number}` : l.note)) : <Badge variant="warning">Pendente</Badge>}</TableCell>
                  <TableCell>{!l.reconciled && can("financeiro.conciliacao", "aprovar") && <Button size="sm" variant="outline" onClick={() => setMatching(l)}><Link2 /> Conciliar</Button>}</TableCell>
                </TableRow>
              ))}
              {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum lançamento." />}
            </TableBody>
          </Table>
          {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
        </Card>
      )}
      {matching && <MatchDialog line={matching} onClose={() => setMatching(null)} onDone={() => mutate()} />}
    </>
  );
}

function MatchDialog({ line, onClose, onDone }: { line: Line; onClose: () => void; onDone: () => void }) {
  const credit = Number(line.amount) > 0;
  const revs = useSWR<Paginated<RevenueRow>>(credit ? "arrecadacao/receitas?ativos=1&page_size=100" : null, fetcher);
  const batches = useSWR<Paginated<{ id: string; number: number; total: string; payment_date: string }>>(!credit ? "financeiro/lotes?page_size=100" : null, fetcher);
  return (
    <FormDialog title="Conciliar lançamento" size="md" onClose={onClose}
      description={`${formatDate(line.date)} · ${line.memo} · ${formatCurrency(line.amount)}. Escolha o lançamento do SIST correspondente ou justifique.`}
      fields={credit
        ? [{ name: "revenue", label: "Receita", type: "select", wide: true, options: (revs.data?.results ?? []).map((r) => ({ value: r.id, label: `${formatDate(r.date)} — ${formatCurrency(r.amount)} — ${r.description || r.kind_display}` })) },
          { name: "note", label: "Ou justificativa (tarifa, estorno etc.)", type: "textarea" }]
        : [{ name: "batch", label: "Lote de pagamento", type: "select", wide: true, options: (batches.data?.results ?? []).map((b) => ({ value: b.id, label: `Lote ${b.number} — ${formatDate(b.payment_date)} — ${formatCurrency(b.total)}` })) },
          { name: "note", label: "Ou justificativa (tarifa, estorno etc.)", type: "textarea" }]}
      submitLabel="Conciliar"
      submit={async (body) => {
        await api(`financeiro/extrato/${line.id}/match`, { method: "POST", body });
        toast.success("Lançamento conciliado.");
        onDone();
      }} />
  );
}

// ------------------------------------------------------------------ Integração contábil
type Mapping = { id: string; plan: string; plan_code: string; source: string; source_display: string; source_code: string; debit: string; credit: string; history: string; active: boolean };
type Preview = { lancamentos: { data: string; debito: string; credito: string; valor: string; historico: string; origem: string }[]; sem_de_para: string[] };
type Export = { id: string; plan_code: string; period: string; lines: number; total: string; sha256: string; unmapped: string[]; user_name: string; created_at: string };

export function AccountingPage() {
  return <RequirePermission module="financeiro.integracao_contabil"><Accounting /></RequirePermission>;
}

function Accounting() {
  const { can } = useSession();
  const plans = usePlans();
  const [plan, setPlan] = useState("");
  const [comp, setComp] = useState(new Date().toISOString().slice(0, 7));
  const [editing, setEditing] = useState<Mapping | "new" | null>(null);
  const maps = useSWR<Paginated<Mapping>>(`financeiro/contabil${qs({ plan: plan || undefined, ativos: 1, page_size: 200 })}`, fetcher);
  const preview = useSWR<Preview>(plan && comp ? `financeiro/contabil/preview${qs({ plan, competence: comp })}` : null, fetcher);
  const exports = useSWR<Paginated<Export>>("financeiro/contabil/exports?page_size=20", fetcher);
  const doExport = async () => {
    try {
      const e = await api<Export>("financeiro/contabil/export", { method: "POST", body: { plan, competence: comp } });
      await download(`financeiro/contabil/exports/${e.id}/download`, "contabil.csv");
      toast.success(`${e.lines} lançamento(s) exportado(s).`);
      exports.mutate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };
  return (
    <>
      <PageHeader title="Integração Contábil" breadcrumb={crumbs("Integração Contábil")}
        description="De-para das rubricas da folha e dos tipos de receita para as contas contábeis (PCASP) de cada plano, e exportação dos lançamentos da competência em planilha (CSV) para o sistema contábil."
        actions={can("financeiro.integracao_contabil", "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Novo de-para</Button>} />
      <Card className="mb-3 flex flex-wrap items-end gap-3 px-4 py-3">
        <FormField label="Plano" htmlFor="ac-plan" className="w-64">
          <Select id="ac-plan" value={plan} onChange={(e) => setPlan(e.target.value)}>
            <option value="">Todos / selecione para exportar</option>
            {plans.data?.results.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>
        </FormField>
        <FormField label="Competência" htmlFor="ac-comp" className="w-44"><Input id="ac-comp" type="month" value={comp} onChange={(e) => setComp(e.target.value)} /></FormField>
        {plan && can("financeiro.integracao_contabil", "exportar") && <Button onClick={doExport} disabled={!preview.data?.lancamentos.length}><Download /> Exportar lançamentos</Button>}
      </Card>
      {plan && preview.data && (
        <Card className="mb-3">
          <div className="border-b px-4 py-2 text-xs font-medium">Prévia — {compLabel(comp + "-01")}</div>
          {preview.data.sem_de_para.length > 0 && <div className="border-b bg-warning/5 px-4 py-2 text-xs text-warning">Sem de-para (ficam fora da exportação): {preview.data.sem_de_para.join("; ")}</div>}
          <Table>
            <TableHeader><TableRow><TableHead>Débito</TableHead><TableHead>Crédito</TableHead><TableHead>Histórico</TableHead><TableHead className="text-right">Valor</TableHead></TableRow></TableHeader>
            <TableBody>
              {preview.data.lancamentos.map((l, i) => <TableRow key={i}><TableCell className="font-mono text-xs">{l.debito}</TableCell><TableCell className="font-mono text-xs">{l.credito}</TableCell><TableCell className="text-xs">{l.historico}</TableCell><TableCell className="text-right tabular">{formatCurrency(l.valor)}</TableCell></TableRow>)}
              {preview.data.lancamentos.length === 0 && <EmptyRow cols={4} text="Nenhum lançamento com de-para na competência (folhas fechadas e receitas)." />}
            </TableBody>
          </Table>
        </Card>
      )}
      <Card className="mb-3">
        <div className="border-b px-4 py-2 text-xs font-medium">De-para contábil</div>
        <Table>
          <TableHeader><TableRow><TableHead>Plano</TableHead><TableHead>Origem</TableHead><TableHead>Débito</TableHead><TableHead>Crédito</TableHead><TableHead>Histórico</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {!maps.data && <LoadingRows cols={6} />}
            {maps.data?.results.map((m) => (
              <TableRow key={m.id}>
                <TableCell><Badge variant="info">{m.plan_code}</Badge></TableCell>
                <TableCell className="text-xs">{m.source_display}: <b>{m.source_code}</b></TableCell>
                <TableCell className="font-mono text-xs">{m.debit}</TableCell><TableCell className="font-mono text-xs">{m.credit}</TableCell>
                <TableCell className="text-xs">{m.history}</TableCell>
                <TableCell>{can("financeiro.integracao_contabil", "editar") && <Button size="sm" variant="ghost" onClick={() => setEditing(m)}>Editar</Button>}</TableCell>
              </TableRow>
            ))}
            {maps.data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum de-para cadastrado." />}
          </TableBody>
        </Table>
      </Card>
      <Card>
        <div className="border-b px-4 py-2 text-xs font-medium">Exportações realizadas</div>
        <Table>
          <TableHeader><TableRow><TableHead>Plano</TableHead><TableHead>Competência</TableHead><TableHead className="text-right">Lançamentos</TableHead><TableHead className="text-right">Total</TableHead><TableHead>Gerado</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {exports.data?.results.map((e) => (
              <TableRow key={e.id}>
                <TableCell>{e.plan_code}</TableCell><TableCell>{compLabel(e.period)}</TableCell>
                <TableCell className="text-right tabular">{e.lines}</TableCell><TableCell className="text-right tabular">{formatCurrency(e.total)}</TableCell>
                <TableCell className="text-xs">{formatDateTime(e.created_at)} · {e.user_name}</TableCell>
                <TableCell><Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Baixar" onClick={() => download(`financeiro/contabil/exports/${e.id}/download`, "contabil.csv")}><Download /></Button></TableCell>
              </TableRow>
            ))}
            {exports.data?.results.length === 0 && <EmptyRow cols={6} text="Nenhuma exportação." />}
          </TableBody>
        </Table>
      </Card>
      {editing && (
        <FormDialog title={editing === "new" ? "Novo de-para contábil" : "Editar de-para"} size="md" onClose={() => setEditing(null)}
          description="Origem RUBRICA: código da rubrica (ex.: 0001). Origem RECEITA: CONTRIBUICAO, APORTE, PARCELAMENTO, COMPREV, RENDIMENTOS ou OUTRAS."
          initial={editing === "new" ? { source: "RUBRICA", plan } : { ...editing }}
          fields={[
            { name: "plan", label: "Plano", type: "select", required: true, options: (plans.data?.results ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.name}` })) },
            { name: "source", label: "Origem", type: "select", required: true, options: [{ value: "RUBRICA", label: "Rubrica da folha" }, { value: "RECEITA", label: "Tipo de receita" }] },
            { name: "source_code", label: "Código", required: true },
            { name: "debit", label: "Conta débito", required: true },
            { name: "credit", label: "Conta crédito", required: true },
            { name: "history", label: "Histórico padrão", wide: true },
            ...(editing === "new" ? [] : [{ name: "active", label: "Ativo", type: "checkbox" as const }]),
          ]}
          submit={async (body) => {
            if (editing === "new") await api("financeiro/contabil", { method: "POST", body });
            else await api(`financeiro/contabil/${editing.id}`, { method: "PATCH", body });
            toast.success("De-para salvo.");
            maps.mutate();
            preview.mutate();
          }} />
      )}
    </>
  );
}
