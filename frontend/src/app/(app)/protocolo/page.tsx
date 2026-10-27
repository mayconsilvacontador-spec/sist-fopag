"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Plus, Search } from "lucide-react";

import { DeadlineBadge, StatusBadge } from "@/components/protocolo/deadline-badge";
import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate, isValidCPF, maskCPF } from "@/lib/format";
import { PRIORITY } from "@/lib/options";
import type { PersonRow, ProcessRow, ProcessTypeRow, Sector } from "@/lib/types";

export default function ProtocolPage() {
  return (
    <RequirePermission module="protocolo.processos">
      <Protocol />
    </RequirePermission>
  );
}

function Protocol() {
  const router = useRouter();
  const { can } = useSession();
  const [caixa, setCaixa] = useState("entrada");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [opening, setOpening] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, error, isLoading } = useSWR<Paginated<ProcessRow>>(
    `protocol/processes${qs({ caixa: caixa === "todos" ? undefined : caixa, search: debounced, status, page })}`,
    fetcher, { keepPreviousData: true },
  );

  return (
    <>
      <PageHeader
        title="Protocolo"
        description="Abertura, tramitação e prazos dos processos."
        breadcrumb={[{ label: "Protocolo" }, { label: "Processos" }]}
        actions={can("protocolo.processos", "incluir") && <Button onClick={() => setOpening(true)}><Plus /> Abrir processo</Button>}
      />
      <Card>
        <div className="flex flex-wrap items-end justify-between gap-3 border-b px-4 pt-2">
          <Tabs value={caixa} onValueChange={(v) => { setCaixa(v); setPage(1); }}>
            <TabsList className="border-b-0">
              <TabsTrigger value="entrada">Caixa do meu setor</TabsTrigger>
              <TabsTrigger value="atrasados">Atrasados</TabsTrigger>
              <TabsTrigger value="todos">Todos</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex flex-wrap items-center gap-2 pb-2">
            <div className="relative w-72">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nº, assunto, interessado ou CPF" className="pl-8" />
            </div>
            {caixa === "todos" && (
              <Select className="w-40" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
                <option value="">Todas</option>
                <option value="EM_TRAMITACAO">Em tramitação</option>
                <option value="SOBRESTADO">Sobrestados</option>
                <option value="CONCLUIDO">Concluídos</option>
                <option value="ARQUIVADO">Arquivados</option>
              </Select>
            )}
          </div>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Processo</TableHead>
              <TableHead>Assunto / interessado</TableHead>
              <TableHead>Setor</TableHead>
              <TableHead>Situação</TableHead>
              <TableHead>Vencimento</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={5} />}
            {data?.results.map((p) => (
              <TableRow key={p.id} className="cursor-pointer" onClick={() => router.push(`/protocolo/processos/${p.id}`)}>
                <TableCell>
                  <div className="font-mono text-xs font-semibold text-primary">{p.code}</div>
                  <div className="text-2xs text-muted-foreground">Aberto em {formatDate(p.opened_date)}</div>
                </TableCell>
                <TableCell>
                  <div className="font-medium">{p.subject}</div>
                  <div className="text-2xs text-muted-foreground">{p.process_type_name} · {p.interested_name}</div>
                </TableCell>
                <TableCell>{p.current_sector_code}</TableCell>
                <TableCell><StatusBadge p={p} /></TableCell>
                <TableCell>{formatDate(p.due_date)}<div><DeadlineBadge p={p} /></div></TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && (
              <EmptyRow cols={5} text={caixa === "entrada" ? "Nenhum processo no(s) seu(s) setor(es)." : "Nenhum processo encontrado."} />
            )}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {opening && <OpenDialog onClose={() => setOpening(false)} onOpened={(p) => router.push(`/protocolo/processos/${p.id}`)} />}
    </>
  );
}

function OpenDialog({ onClose, onOpened }: { onClose: () => void; onOpened: (p: ProcessRow) => void }) {
  const types = useSWR<Paginated<ProcessTypeRow>>("protocol/process-types?ativos=1&page_size=200", fetcher);
  // Todos os setores ativos (os do usuário primeiro): qualquer setor pode abrir processo para outro
  const sectors = useSWR<(Sector & { meu: boolean })[]>("protocol/sectors/destinos", fetcher);
  const ordered = [...(sectors.data ?? [])].sort((a, b) => Number(b.meu) - Number(a.meu));
  const [f, setF] = useState({ process_type: "", sector: "", subject: "", description: "", priority: "NORMAL",
    external_number: "", cpf: "", interested_name: "" });
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));

  useEffect(() => {
    if (sectors.data?.length && !f.sector) {
      const first = sectors.data.find((s) => s.meu) ?? sectors.data[0];
      setF((s) => ({ ...s, sector: first.id }));
    }
  }, [sectors.data, f.sector]);
  const target = sectors.data?.find((s) => s.id === f.sector);

  const lookup = async (cpf: string) => {
    setPerson(null);
    if (!isValidCPF(cpf)) return;
    const found = await api<PersonRow | null>(`people/by-cpf${qs({ cpf })}`).catch(() => null);
    if (found) { setPerson(found); setF((s) => ({ ...s, interested_name: found.name })); }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      const p = await api<ProcessRow>("protocol/processes", {
        method: "POST",
        body: { process_type: f.process_type, sector: f.sector, subject: f.subject, description: f.description,
          priority: f.priority, external_number: f.external_number, interested: person?.id ?? null,
          interested_name: f.interested_name, interested_cpf: f.cpf },
      });
      toast.success(`Processo ${p.code} aberto.`);
      onOpened(p);
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const type = types.data?.results.find((t) => t.id === f.process_type);

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader>
            <DialogTitle>Abrir processo</DialogTitle>
            <DialogDescription>O número é gerado automaticamente (sequencial por ano). O prazo vem do tipo de processo.</DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            {sectors.data && sectors.data.length === 0 && (
              <div className="rounded-md border border-warning-border bg-warning-soft px-3 py-2 text-xs text-warning sm:col-span-2">
                Nenhum setor ativo cadastrado. Peça ao gestor para cadastrar os setores em Protocolo › Configuração › Setores.
              </div>
            )}
            <FormField label="Tipo de processo" htmlFor="o-type" required error={errors.process_type}
              hint={type ? `Prazo: ${type.deadline_days} dia(s) ${type.business_days ? "úteis" : "corridos"}` : undefined}>
              <Select id="o-type" value={f.process_type} onChange={set("process_type")} required>
                <option value="">Selecione</option>
                {types.data?.results.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
            </FormField>
            <FormField label="Setor de destino" htmlFor="o-sector" required error={errors.sector}
              hint={target && !target.meu ? "Você não é deste setor: o processo chega lá aguardando recebimento." : undefined}>
              <Select id="o-sector" value={f.sector} onChange={set("sector")} required>
                {ordered.map((s) => <option key={s.id} value={s.id}>{s.code} - {s.name}{s.meu ? " (meu setor)" : ""}</option>)}
              </Select>
            </FormField>
            <FormField label="Assunto" htmlFor="o-subject" required error={errors.subject} className="sm:col-span-2">
              <Input id="o-subject" value={f.subject} onChange={set("subject")} required />
            </FormField>
            <FormField label="CPF do interessado" htmlFor="o-cpf" error={errors.interested_cpf}
              hint={person ? "Encontrado no Cadastro Único." : "Se estiver no Cadastro Único, o processo é vinculado à pessoa."}>
              <Input id="o-cpf" value={f.cpf} inputMode="numeric" placeholder="000.000.000-00"
                onChange={(e) => { const v = maskCPF(e.target.value); setF((s) => ({ ...s, cpf: v })); lookup(v); }} />
            </FormField>
            <FormField label="Interessado" htmlFor="o-name" required error={errors.interested_name}>
              <Input id="o-name" value={f.interested_name} onChange={set("interested_name")} disabled={!!person} required />
            </FormField>
            <FormField label="Prioridade" htmlFor="o-priority">
              <Select id="o-priority" value={f.priority} onChange={set("priority")}>
                {PRIORITY.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </FormField>
            <FormField label="Nº de origem / externo" htmlFor="o-ext">
              <Input id="o-ext" value={f.external_number} onChange={set("external_number")} />
            </FormField>
            <FormField label="Descrição / requerimento" htmlFor="o-desc" className="sm:col-span-2">
              <Textarea id="o-desc" value={f.description} onChange={set("description")} />
            </FormField>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button type="submit" disabled={busy || !sectors.data?.length}>{busy && <Loader2 className="animate-spin" />} Abrir processo</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
