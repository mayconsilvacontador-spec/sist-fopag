"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Plus } from "lucide-react";

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
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import type { CtcRow, PersonRow } from "@/lib/types";

export default function CtcPage() {
  return (
    <RequirePermission module="previdenciaria.ctc">
      <CtcList />
    </RequirePermission>
  );
}

function CtcList() {
  const router = useRouter();
  const { can } = useSession();
  const [page, setPage] = useState(1);
  const [issuing, setIssuing] = useState(false);
  const { data, error, isLoading } = useSWR<Paginated<CtcRow>>(`previdencia/ctc${qs({ page })}`, fetcher, { keepPreviousData: true });

  return (
    <>
      <PageHeader
        title="Certidão de Tempo de Contribuição"
        description="CTC para ex-servidores averbarem o tempo em outro regime (contagem recíproca). O conteúdo é congelado na emissão."
        breadcrumb={[{ label: "Gestão Previdenciária" }, { label: "CTC" }]}
        actions={can("previdenciaria.ctc", "incluir") && <Button onClick={() => setIssuing(true)}><Plus /> Emitir CTC</Button>}
      />
      <Card>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Nº</TableHead><TableHead>Segurado</TableHead><TableHead>Período certificado</TableHead><TableHead>Destino</TableHead><TableHead>Tempo líquido</TableHead><TableHead>Situação</TableHead><TableHead>Emissão</TableHead></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={7} />}
            {data?.results.map((c) => (
              <TableRow key={c.id} className="cursor-pointer" onClick={() => router.push(`/previdenciaria/ctc/${c.id}`)}>
                <TableCell className="font-mono text-xs font-semibold text-primary">{c.code}</TableCell>
                <TableCell>{c.person_name}</TableCell>
                <TableCell className="text-xs">{formatDate(c.period_start)} a {formatDate(c.period_end)}</TableCell>
                <TableCell className="text-xs">{c.destination}</TableCell>
                <TableCell className="text-xs">{c.snapshot.totais.liquido_texto}</TableCell>
                <TableCell>{c.status === "EMITIDA" ? <Badge variant="success">Emitida</Badge> : <Badge variant="neutral">Cancelada</Badge>}</TableCell>
                <TableCell className="text-xs">{formatDateTime(c.created_at)}<div className="text-2xs text-muted-foreground">{c.issued_by}</div></TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={7} text="Nenhuma CTC emitida." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {issuing && <IssueDialog onClose={() => setIssuing(false)} onIssued={(c) => router.push(`/previdenciaria/ctc/${c.id}`)} />}
    </>
  );
}

function IssueDialog({ onClose, onIssued }: { onClose: () => void; onIssued: (c: CtcRow) => void }) {
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [f, setF] = useState({ destination: "", purpose: "Averbação / contagem recíproca", period_start: "", period_end: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!person) { toast.error("Escolha o segurado."); return; }
    setBusy(true);
    setErrors({});
    try {
      const c = await api<CtcRow>("previdencia/ctc", { method: "POST", body: { ...f, person: person.id } });
      toast.success(`CTC ${c.code} emitida.`);
      onIssued(c);
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
            <DialogTitle>Emitir CTC</DialogTitle>
            <DialogDescription>Somente para ex-servidor (vínculo encerrado) e tempo não utilizado em aposentadoria neste RPPS. Não pode haver outra CTC para o mesmo período.</DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2"><PersonPicker value={person} onChange={setPerson} /></div>
            <FormField label="Período certificado — início" htmlFor="c-start" required error={errors.period_start}>
              <Input id="c-start" type="date" value={f.period_start} onChange={set("period_start")} required />
            </FormField>
            <FormField label="Período certificado — fim" htmlFor="c-end" required error={errors.period_end}>
              <Input id="c-end" type="date" value={f.period_end} onChange={set("period_end")} required />
            </FormField>
            <FormField label="Órgão / regime de destino" htmlFor="c-dest" required error={errors.destination} className="sm:col-span-2">
              <Input id="c-dest" value={f.destination} onChange={set("destination")} required placeholder="Ex.: INSS / RPPS do Município de ..." />
            </FormField>
            <FormField label="Finalidade" htmlFor="c-purpose" className="sm:col-span-2">
              <Input id="c-purpose" value={f.purpose} onChange={set("purpose")} />
            </FormField>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Emitir</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
