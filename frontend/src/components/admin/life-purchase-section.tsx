"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Pencil, Plus } from "lucide-react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox, Input, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher, type Paginated } from "@/lib/api";
import { formatCurrency, formatDate, formatInt } from "@/lib/format";
import type { LifePurchase, PayrollGroup } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Folhas de benefícios (uma por massa) e Compra de Vidas.
 * A Compra de Vidas pertence ao Plano Previdenciário (fundo em capitalização),
 * mas tem folha própria para ser identificada na avaliação atuarial e na contabilidade.
 */
export function LifePurchaseSection({
  enabled, canEdit, canCreate, onChanged,
}: {
  enabled: boolean;
  canEdit: boolean;
  canCreate: boolean;
  onChanged: () => void;
}) {
  const groups = useSWR<PayrollGroup[]>("payroll-groups", fetcher);
  const lots = useSWR<Paginated<LifePurchase>>("life-purchases?page_size=100", fetcher);
  const [confirm, setConfirm] = useState(false);
  const [editing, setEditing] = useState<LifePurchase | "new" | null>(null);

  const toggle = async (justification: string) => {
    try {
      await api("institution/current/life-purchase", { method: "POST", body: { enabled: !enabled, justification } });
      toast.success(enabled ? "Compra de Vidas desativada." : "Compra de Vidas ativada. A folha PREV-CV foi criada.");
      groups.mutate();
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
      throw err;
    }
  };

  const lotList = lots.data?.results ?? [];

  return (
    <Card className="xl:col-span-5">
      <CardHeader>
        <CardTitle>Folhas de benefícios e Compra de Vidas</CardTitle>
      </CardHeader>

      <div className="grid gap-4 p-4 lg:grid-cols-5">
        {/* Interruptor */}
        <div className="space-y-3 lg:col-span-2">
          <div className="flex items-center justify-between gap-3 rounded-md border bg-muted/40 px-3 py-2.5">
            <div>
              <div className="text-xs font-semibold">Este RPPS possui Compra de Vidas?</div>
              <div className="text-2xs text-muted-foreground">
                Vidas transferidas do Plano Financeiro para o Plano Previdenciário.
              </div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-label="Possui Compra de Vidas"
              disabled={!canEdit}
              onClick={() => setConfirm(true)}
              className={cn(
                "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                enabled ? "bg-primary" : "bg-input",
              )}
            >
              <span className={cn("inline-block h-4 w-4 rounded-full bg-white shadow transition-transform", enabled ? "translate-x-4" : "translate-x-0.5")} />
            </button>
          </div>
          <p className="text-2xs leading-relaxed text-muted-foreground">
            Com a Compra de Vidas ativada, o sistema passa a ter <strong>três folhas</strong>: Financeiro,
            Previdenciário (massa própria) e Compra de Vidas. A Compra de Vidas continua pertencendo ao
            <strong> Plano Previdenciário (fundo em capitalização)</strong> — por isso o filtro
            &quot;Previdenciário&quot; mostra o consolidado e permite separar as duas folhas. Na base atuarial,
            essas vidas vão no arquivo do fundo em capitalização e também em um arquivo complementar que as identifica.
          </p>
        </div>

        {/* Folhas */}
        <div className="lg:col-span-3">
          <div className="section-label mb-2">Folhas</div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Código</TableHead>
                <TableHead>Folha</TableHead>
                <TableHead>Plano / fundo</TableHead>
                <TableHead>Situação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.isLoading && <LoadingRows cols={4} rows={2} />}
              {groups.data?.map((g) => (
                <TableRow key={g.id} className={cn(!g.active && "opacity-60")}>
                  <TableCell className="font-mono text-xs font-semibold">{g.code}</TableCell>
                  <TableCell className="font-medium">{g.name}</TableCell>
                  <TableCell className="text-xs">
                    {g.plan_code} · {g.plan_kind === "FINANCEIRO" ? "Repartição" : "Capitalização"}
                  </TableCell>
                  <TableCell>{g.active ? <Badge variant="success">Ativa</Badge> : <Badge variant="neutral">Inativa</Badge>}</TableCell>
                </TableRow>
              ))}
              {groups.data && groups.data.length === 0 && <EmptyRow cols={4} text="Cadastre os planos para criar as folhas." />}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Lotes */}
      {(enabled || lotList.length > 0) && (
        <div className="border-t">
          <div className="flex items-center justify-between px-4 py-2.5">
            <div className="section-label">Lotes de Compra de Vidas</div>
            {canCreate && enabled && (
              <Button size="sm" variant="outline" onClick={() => setEditing("new")}><Plus /> Novo lote</Button>
            )}
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Lote</TableHead>
                <TableHead>Data de corte</TableHead>
                <TableHead>Ato legal</TableHead>
                <TableHead className="text-right">Valor transferido</TableHead>
                <TableHead className="text-right">Vidas</TableHead>
                <TableHead>Situação</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {lots.isLoading && <LoadingRows cols={7} rows={1} />}
              {lotList.map((l) => (
                <TableRow key={l.id}>
                  <TableCell className="font-mono text-xs font-semibold">{l.number}</TableCell>
                  <TableCell>{formatDate(l.cutoff_date)}</TableCell>
                  <TableCell>
                    <div className="font-medium">{l.legal_act}</div>
                    {l.actuarial_study && <div className="text-2xs text-muted-foreground">{l.actuarial_study}</div>}
                  </TableCell>
                  <TableCell className="text-right tabular">{l.transferred_amount ? formatCurrency(l.transferred_amount) : "—"}</TableCell>
                  <TableCell className="text-right tabular">{l.lives_count != null ? formatInt(l.lives_count) : "—"}</TableCell>
                  <TableCell>{l.active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}</TableCell>
                  <TableCell>
                    {canEdit && <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(l)} aria-label="Editar"><Pencil /></Button>}
                  </TableCell>
                </TableRow>
              ))}
              {lots.data && lotList.length === 0 && (
                <EmptyRow cols={7} text="Nenhum lote registrado. Registre a data de corte e o ato legal da operação." />
              )}
            </TableBody>
          </Table>
          <p className="border-t px-4 py-2.5 text-2xs text-muted-foreground">
            Cada beneficiário da folha da Compra de Vidas será vinculado ao lote que o transferiu (a partir das Fases 4 e 5).
            Lotes não são excluídos — apenas inativados.
          </p>
        </div>
      )}

      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={enabled ? "Desativar Compra de Vidas" : "Ativar Compra de Vidas"}
        description={
          enabled
            ? "A folha da Compra de Vidas será inativada. Só é possível se não houver lotes ativos."
            : "Será criada a folha PREV-CV, vinculada ao Plano Previdenciário (fundo em capitalização)."
        }
        confirmLabel={enabled ? "Desativar" : "Ativar"}
        destructive={enabled}
        requireJustification
        onConfirm={toggle}
      />
      {editing && (
        <LotDialog lot={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { lots.mutate(); onChanged(); }} />
      )}
    </Card>
  );
}

/** Aceita "1.500.000,00" (padrão brasileiro) ou "1500000.00" (valor vindo da API). */
function parseAmount(value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  return v.includes(",") ? v.replace(/\./g, "").replace(",", ".") : v;
}

function LotDialog({ lot, onClose, onSaved }: { lot: LifePurchase | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    cutoff_date: lot?.cutoff_date ?? "",
    effective_date: lot?.effective_date ?? "",
    legal_act: lot?.legal_act ?? "",
    legal_act_date: lot?.legal_act_date ?? "",
    actuarial_study: lot?.actuarial_study ?? "",
    transferred_amount: lot?.transferred_amount ?? "",
    lives_count: lot?.lives_count != null ? String(lot.lives_count) : "",
    notes: lot?.notes ?? "",
    active: lot?.active ?? true,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      const body = {
        ...form,
        effective_date: form.effective_date || null,
        legal_act_date: form.legal_act_date || null,
        transferred_amount: parseAmount(form.transferred_amount),
        lives_count: form.lives_count ? Number(form.lives_count) : null,
      };
      if (lot) await api(`life-purchases/${lot.id}`, { method: "PATCH", body });
      else await api("life-purchases", { method: "POST", body });
      toast.success("Lote salvo.");
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
            <DialogTitle>{lot ? `Lote ${lot.number} de Compra de Vidas` : "Novo lote de Compra de Vidas"}</DialogTitle>
            <DialogDescription>Origem: Plano Financeiro · Destino: Plano Previdenciário. Alterações são auditadas.</DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <FormField label="Data de corte" htmlFor="l-cut" required error={errors.cutoff_date}>
              <Input id="l-cut" type="date" value={form.cutoff_date} onChange={set("cutoff_date")} required />
            </FormField>
            <FormField label="Início do pagamento pelo Previdenciário" htmlFor="l-eff" error={errors.effective_date}>
              <Input id="l-eff" type="date" value={form.effective_date} onChange={set("effective_date")} />
            </FormField>
            <FormField label="Ato legal" htmlFor="l-act" required error={errors.legal_act} className="sm:col-span-2" hint="Ex.: Lei Municipal nº 0.000/2025.">
              <Input id="l-act" value={form.legal_act} onChange={set("legal_act")} required />
            </FormField>
            <FormField label="Data do ato legal" htmlFor="l-actd" error={errors.legal_act_date}>
              <Input id="l-actd" type="date" value={form.legal_act_date} onChange={set("legal_act_date")} />
            </FormField>
            <FormField label="Estudo atuarial" htmlFor="l-study" error={errors.actuarial_study}>
              <Input id="l-study" value={form.actuarial_study} onChange={set("actuarial_study")} placeholder="Parecer / relatório" />
            </FormField>
            <FormField label="Valor transferido (R$)" htmlFor="l-amount" error={errors.transferred_amount}>
              <Input id="l-amount" inputMode="decimal" value={form.transferred_amount} onChange={set("transferred_amount")} placeholder="0,00" />
            </FormField>
            <FormField label="Quantidade de vidas (informada)" htmlFor="l-lives" error={errors.lives_count}>
              <Input id="l-lives" type="number" min={0} value={form.lives_count} onChange={set("lives_count")} />
            </FormField>
            <FormField label="Observações" htmlFor="l-notes" error={errors.notes} className="sm:col-span-2">
              <Textarea id="l-notes" value={form.notes} onChange={set("notes")} />
            </FormField>
            {lot && (
              <label className="flex items-center gap-2 text-xs">
                <Checkbox checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Lote ativo
              </label>
            )}
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
