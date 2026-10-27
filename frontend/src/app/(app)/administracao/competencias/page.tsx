"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Lock, LockOpen, Plus, Star } from "lucide-react";

import { useAppState } from "@/components/providers/app-state";
import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { StatusBadge } from "@/components/shared/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher, qs, type Paginated } from "@/lib/api";
import { MONTHS, formatDateTime } from "@/lib/format";
import type { Competence } from "@/lib/types";

export default function CompetencesPage() {
  return (
    <RequirePermission module="admin.competencias">
      <Competences />
    </RequirePermission>
  );
}

type PendingAction = { kind: "close" | "reopen" | "set-reference"; comp: Competence } | null;

function Competences() {
  const { can } = useSession();
  const { exercise } = useAppState();
  const [year, setYear] = useState<string>(String(exercise));
  const { data, error, isLoading, mutate } = useSWR<Paginated<Competence>>(`competences${qs({ year, page_size: 50 })}`, fetcher);
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState<PendingAction>(null);

  const titles = {
    close: { t: "Fechar competência", d: "Após o fechamento, a competência não aceita alterações sem reabertura formal.", l: "Fechar" },
    reopen: { t: "Reabrir competência", d: "A reabertura será registrada na auditoria com a justificativa informada.", l: "Reabrir" },
    "set-reference": { t: "Definir competência de referência", d: "A competência de referência é exibida no Painel Geral e orienta as rotinas mensais.", l: "Definir" },
  };

  return (
    <>
      <PageHeader
        title="Competências"
        description="Meses de referência da instituição. O ciclo da folha (aberta → calculada → fechada → paga) será controlado na Fase 5."
        breadcrumb={[{ label: "Administração" }, { label: "Competências" }]}
        actions={can("admin.competencias", "incluir") && <Button onClick={() => setCreating(true)}><Plus /> Nova competência</Button>}
      />
      <Card>
        <div className="flex items-center gap-2 border-b px-4 py-2.5">
          <Label htmlFor="ano">Ano</Label>
          <Input id="ano" type="number" className="w-28" value={year} onChange={(e) => setYear(e.target.value)} />
          <Button variant="ghost" size="sm" onClick={() => setYear("")}>Todos</Button>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Competência</TableHead>
              <TableHead>Descrição</TableHead>
              <TableHead>Situação</TableHead>
              <TableHead>Fechamento</TableHead>
              <TableHead className="w-64 text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <LoadingRows cols={5} rows={3} />}
            {data?.results.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-semibold tabular">
                  {c.code} {c.is_reference && <Badge variant="info" className="ml-1"><Star className="h-3 w-3" /> Referência</Badge>}
                </TableCell>
                <TableCell>{c.label}</TableCell>
                <TableCell><StatusBadge status={c.status} label={c.status_display} /></TableCell>
                <TableCell className="text-xs text-muted-foreground">{c.closed_at ? `${formatDateTime(c.closed_at)} · ${c.closed_by_name}` : "—"}</TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    {!c.is_reference && can("admin.competencias", "editar") && (
                      <Button size="sm" variant="outline" onClick={() => setPending({ kind: "set-reference", comp: c })}><Star /> Referência</Button>
                    )}
                    {c.status === "ABERTA" && can("admin.competencias", "fechar") && (
                      <Button size="sm" variant="outline" onClick={() => setPending({ kind: "close", comp: c })}><Lock /> Fechar</Button>
                    )}
                    {c.status === "FECHADA" && can("admin.competencias", "reabrir") && (
                      <Button size="sm" variant="outline" onClick={() => setPending({ kind: "reopen", comp: c })}><LockOpen /> Reabrir</Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={5} />}
          </TableBody>
        </Table>
      </Card>

      {creating && <CreateDialog defaultYear={Number(year) || new Date().getFullYear()} onClose={() => setCreating(false)} onSaved={() => mutate()} />}
      {pending && (
        <ConfirmDialog
          open
          onOpenChange={(v) => !v && setPending(null)}
          title={`${titles[pending.kind].t} ${pending.comp.code}`}
          description={titles[pending.kind].d}
          confirmLabel={titles[pending.kind].l}
          requireJustification={pending.kind === "reopen"}
          destructive={pending.kind === "reopen"}
          onConfirm={async (justification) => {
            try {
              await api(`competences/${pending.comp.id}/${pending.kind}`, { method: "POST", body: { justification } });
              toast.success("Operação realizada.");
              mutate();
            } catch (e) {
              toast.error((e as Error).message);
              throw e;
            }
          }}
        />
      )}
    </>
  );
}

function CreateDialog({ defaultYear, onClose, onSaved }: { defaultYear: number; onClose: () => void; onSaved: () => void }) {
  const [year, setYear] = useState(String(defaultYear));
  const [month, setMonth] = useState(String(new Date().getMonth() + 1));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api("competences", { method: "POST", body: { year: Number(year), month: Number(month) } });
      toast.success("Competência cadastrada.");
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
      <DialogContent size="sm">
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader><DialogTitle>Nova competência</DialogTitle></DialogHeader>
          <DialogBody className="grid grid-cols-2 gap-3">
            <FormField label="Mês" htmlFor="month" required error={errors.month}>
              <Select id="month" value={month} onChange={(e) => setMonth(e.target.value)}>
                {MONTHS.map((m, i) => <option key={m} value={i + 1}>{String(i + 1).padStart(2, "0")} - {m}</option>)}
              </Select>
            </FormField>
            <FormField label="Ano" htmlFor="year" required error={errors.year}>
              <Input id="year" type="number" value={year} onChange={(e) => setYear(e.target.value)} required />
            </FormField>
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
