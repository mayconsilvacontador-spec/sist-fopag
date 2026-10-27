"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Plus, Search } from "lucide-react";

import { BenefitPicker } from "@/components/folha/benefit-picker";
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
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import type { BenefitRow, Concession, ConcessionRow, ConcessionStage, PersonRow, ProcessRow } from "@/lib/types";

export const STAGE_VARIANT: Record<ConcessionStage, "default" | "info" | "success" | "warning" | "neutral" | "critical"> = {
  INSTRUCAO: "neutral", ENQUADRADO: "info", CALCULADO: "info", ANALISE_JURIDICA: "warning", CONTROLE_INTERNO: "warning",
  PRESIDENCIA: "warning", ATO_EMITIDO: "default", PUBLICADO: "default", IMPLANTADO: "success", INDEFERIDO: "critical",
  ANULADO: "critical", SOBRESTADO: "warning", DESISTENCIA: "neutral",
};

type Kind = "APOSENTADORIA" | "PENSAO" | "REVISAO" | undefined;

export function ConcessionListPage({ kind, title, description }: { kind: Kind; title: string; description: string }) {
  const moduleCode = kind === "APOSENTADORIA" ? "concessao.aposentadoria" : kind === "PENSAO" ? "concessao.pensao" : kind === "REVISAO" ? "concessao.revisao" : "concessao.processos";
  return (
    <RequirePermission module={moduleCode}>
      <List kind={kind} title={title} description={description} />
    </RequirePermission>
  );
}

function List({ kind, title, description }: { kind: Kind; title: string; description: string }) {
  const router = useRouter();
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [stage, setStage] = useState("");
  const [page, setPage] = useState(1);
  const [opening, setOpening] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const { data, error, isLoading } = useSWR<Paginated<ConcessionRow>>(
    `concessoes${qs({ kind, stage, search: debounced, page })}`, fetcher, { keepPreviousData: true });
  const canOpen = kind === "REVISAO" ? can("concessao.revisao", "incluir") : can("concessao.aposentadoria", "incluir") || can("concessao.pensao", "incluir");

  return (
    <>
      <PageHeader title={title} description={description} breadcrumb={[{ label: "Concessão de Benefícios" }, { label: title }]}
        actions={canOpen && <Button onClick={() => setOpening(true)}><Plus /> Nova concessão</Button>} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome, CPF ou nº do processo" className="pl-8" />
          </div>
          <Select className="w-48" value={stage} onChange={(e) => { setStage(e.target.value); setPage(1); }} aria-label="Etapa">
            <option value="">Todas as etapas</option>
            {Object.keys(STAGE_VARIANT).map((s) => <option key={s} value={s}>{s.replace("_", " ").toLowerCase()}</option>)}
          </Select>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Processo</TableHead><TableHead>Tipo</TableHead><TableHead>Servidor / instituidor</TableHead><TableHead>Regra</TableHead><TableHead>Validade</TableHead><TableHead className="text-right">Valor</TableHead><TableHead>Etapa</TableHead></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={7} />}
            {data?.results.map((c) => (
              <TableRow key={c.id} className="cursor-pointer" onClick={() => router.push(`/concessao/processo/${c.id}`)}>
                <TableCell className="font-mono text-xs font-semibold text-primary">{c.process_code}</TableCell>
                <TableCell>{c.kind_display}</TableCell>
                <TableCell className="font-medium">{c.person_name}</TableCell>
                <TableCell className="text-xs">{c.rule_name || "—"}</TableCell>
                <TableCell>{formatDate(c.validity_date)}</TableCell>
                <TableCell className="text-right tabular">{c.total ? formatCurrency(c.total) : "—"}</TableCell>
                <TableCell><Badge variant={STAGE_VARIANT[c.stage]}>{c.stage_display}</Badge></TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={7} text="Nenhum processo de concessão." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {opening && <OpenDialog defaultKind={kind} onClose={() => setOpening(false)} onOpened={(c) => router.push(`/concessao/processo/${c.id}`)} />}
    </>
  );
}

function OpenDialog({ defaultKind, onClose, onOpened }: { defaultKind: Kind; onClose: () => void; onOpened: (c: Concession) => void }) {
  const [kind, setKind] = useState<string>(defaultKind ?? "APOSENTADORIA");
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [benefit, setBenefit] = useState<BenefitRow | null>(null);
  const revisao = kind === "REVISAO";
  const interestedId = revisao ? benefit?.beneficiary : person?.id;
  const [procSearch, setProcSearch] = useState("");
  const [processId, setProcessId] = useState("");
  const [busy, setBusy] = useState(false);
  const processes = useSWR<Paginated<ProcessRow>>(
    interestedId ? `protocol/processes${qs({ interested: interestedId, status: "EM_TRAMITACAO", page_size: 20 })}`
      : procSearch.length >= 3 ? `protocol/processes${qs({ search: procSearch, status: "EM_TRAMITACAO", page_size: 20 })}` : null,
    fetcher);

  const submit = async () => {
    if ((revisao ? !benefit : !person) || !processId) { toast.error(revisao ? "Escolha o benefício e o processo do Protocolo." : "Escolha a pessoa e o processo do Protocolo."); return; }
    setBusy(true);
    try {
      const c = await api<Concession>("concessoes", { method: "POST", body: revisao ? { kind, benefit: benefit!.id, process: processId } : { kind, person: person!.id, process: processId } });
      toast.success("Processo de concessão aberto.");
      onOpened(c);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Nova concessão</DialogTitle>
          <DialogDescription>Toda concessão nasce de um processo aberto no Protocolo (requerimento do servidor ou dos dependentes).</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormField label="Tipo de benefício" htmlFor="o-kind">
            <Select id="o-kind" value={kind} onChange={(e) => setKind(e.target.value)} disabled={!!defaultKind}>
              <option value="APOSENTADORIA">Aposentadoria</option>
              <option value="PENSAO">Pensão por morte</option>
              <option value="REVISAO">Revisão de benefício</option>
            </Select>
          </FormField>
          {revisao ? (<div>
            <div className="mb-1 text-xs font-medium text-foreground/80">Benefício a revisar</div>
            <BenefitPicker value={benefit} onChange={(b) => { setBenefit(b); setProcessId(""); }} />
            <p className="mt-1 text-2xs text-muted-foreground">A revisão segue Jurídico → Presidência (portaria) → publicação → folha. O valor só muda na implantação.</p>
          </div>) : (<div>
            <div className="mb-1 text-xs font-medium text-foreground/80">{kind === "PENSAO" ? "Instituidor (servidor/aposentado falecido)" : "Servidor"}</div>
            <PersonPicker value={person} onChange={(p) => { setPerson(p); setProcessId(""); }} />
            {kind === "PENSAO" && <p className="mt-1 text-2xs text-muted-foreground">A data do óbito deve estar no Cadastro Único do instituidor.</p>}
          </div>)}
          <FormField label="Processo do Protocolo" htmlFor="o-proc" hint={interestedId ? "Processos em tramitação em que a pessoa é interessada." : "Escolha a pessoa ou busque pelo número."}>
            {!interestedId && <Input id="o-proc-search" className="mb-2" value={procSearch} onChange={(e) => setProcSearch(e.target.value)} placeholder="Nº do processo (ex.: 000012/2026)" />}
            <Select id="o-proc" value={processId} onChange={(e) => setProcessId(e.target.value)}>
              <option value="">Selecione</option>
              {processes.data?.results.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.subject}</option>)}
            </Select>
            {processes.data && processes.data.results.length === 0 && (
              <p className="mt-1 text-2xs text-warning">Nenhum processo em tramitação encontrado. Abra o requerimento no Protocolo primeiro.</p>
            )}
          </FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={busy}>{busy && <Loader2 className="animate-spin" />} Abrir concessão</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
