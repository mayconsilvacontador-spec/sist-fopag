"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Lock, LockOpen, Plus } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { StatusBadge } from "@/components/shared/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher, type Paginated } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { FiscalYear } from "@/lib/types";

export default function FiscalYearsPage() {
  return (
    <RequirePermission module="admin.exercicios">
      <FiscalYears />
    </RequirePermission>
  );
}

function FiscalYears() {
  const { can } = useSession();
  const { data, error, isLoading, mutate } = useSWR<Paginated<FiscalYear>>("fiscal-years?page_size=50", fetcher);
  const [creating, setCreating] = useState(false);
  const [action, setAction] = useState<{ kind: "close" | "reopen"; fy: FiscalYear } | null>(null);

  return (
    <>
      <PageHeader
        title="Exercícios"
        description="Um exercício fechado impede novas competências. A reabertura exige justificativa e é auditada."
        breadcrumb={[{ label: "Administração" }, { label: "Exercícios" }]}
        actions={can("admin.exercicios", "incluir") && <Button onClick={() => setCreating(true)}><Plus /> Novo exercício</Button>}
      />
      <Card>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Exercício</TableHead>
              <TableHead>Situação</TableHead>
              <TableHead className="text-right">Competências</TableHead>
              <TableHead>Fechamento</TableHead>
              <TableHead>Observações</TableHead>
              <TableHead className="w-32 text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <LoadingRows cols={6} rows={3} />}
            {data?.results.map((fy) => (
              <TableRow key={fy.id}>
                <TableCell className="text-[15px] font-bold text-primary">{fy.year}</TableCell>
                <TableCell><StatusBadge status={fy.status} label={fy.status_display} /></TableCell>
                <TableCell className="text-right tabular">{fy.competences_count}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {fy.closed_at ? `${formatDateTime(fy.closed_at)} · ${fy.closed_by_name}` : "—"}
                </TableCell>
                <TableCell className="max-w-xs truncate text-xs">{fy.notes || "—"}</TableCell>
                <TableCell className="text-right">
                  {fy.status === "ABERTO" && can("admin.exercicios", "fechar") && (
                    <Button size="sm" variant="outline" onClick={() => setAction({ kind: "close", fy })}><Lock /> Fechar</Button>
                  )}
                  {fy.status === "FECHADO" && can("admin.exercicios", "reabrir") && (
                    <Button size="sm" variant="outline" onClick={() => setAction({ kind: "reopen", fy })}><LockOpen /> Reabrir</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={6} />}
          </TableBody>
        </Table>
      </Card>

      {creating && <CreateDialog onClose={() => setCreating(false)} onSaved={() => mutate()} />}
      {action && (
        <ConfirmDialog
          open
          onOpenChange={(v) => !v && setAction(null)}
          title={action.kind === "close" ? `Fechar exercício ${action.fy.year}` : `Reabrir exercício ${action.fy.year}`}
          description={action.kind === "close"
            ? "Todas as competências do exercício precisam estar fechadas."
            : "A reabertura permite novas alterações no exercício e ficará registrada com a justificativa."}
          confirmLabel={action.kind === "close" ? "Fechar exercício" : "Reabrir exercício"}
          requireJustification={action.kind === "reopen"}
          destructive={action.kind === "reopen"}
          onConfirm={async (justification) => {
            try {
              await api(`fiscal-years/${action.fy.id}/${action.kind}`, { method: "POST", body: { justification } });
              toast.success(action.kind === "close" ? "Exercício fechado." : "Exercício reaberto.");
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

function CreateDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [year, setYear] = useState(String(new Date().getFullYear() + 1));
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api("fiscal-years", { method: "POST", body: { year: Number(year), notes } });
      toast.success("Exercício cadastrado.");
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
          <DialogHeader><DialogTitle>Novo exercício</DialogTitle></DialogHeader>
          <DialogBody className="space-y-3">
            <FormField label="Ano" htmlFor="year" required error={errors.year}>
              <Input id="year" type="number" min={1990} max={2100} value={year} onChange={(e) => setYear(e.target.value)} required />
            </FormField>
            <FormField label="Observações" htmlFor="notes" error={errors.notes}>
              <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
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
