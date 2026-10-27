"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { History, Loader2, Plus } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox, Input, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import type { Parameter } from "@/lib/types";

export default function ParametersPage() {
  return (
    <RequirePermission module="admin.parametros">
      <Parameters />
    </RequirePermission>
  );
}

function showValue(v: unknown) {
  return typeof v === "string" ? v : JSON.stringify(v);
}

function Parameters() {
  const { can } = useSession();
  const params = useSearchParams();
  const [onlyCurrent, setOnlyCurrent] = useState(true);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState<{ key?: string; description?: string } | null>(null);
  const [historyKey, setHistoryKey] = useState<string | null>(params.get("key"));

  const { data, error, isLoading, mutate } = useSWR<Paginated<Parameter>>(
    `parameters${qs({ vigentes: onlyCurrent ? 1 : undefined, search, page_size: 200 })}`,
    fetcher,
  );

  return (
    <>
      <PageHeader
        title="Parâmetros"
        description="Parâmetros versionados por vigência. Nenhum valor é sobrescrito: uma alteração gera nova versão e encerra a anterior."
        breadcrumb={[{ label: "Administração" }, { label: "Parâmetros" }]}
        actions={can("admin.parametros", "incluir") && <Button onClick={() => setCreating({})}><Plus /> Novo parâmetro</Button>}
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <Input className="max-w-xs" placeholder="Buscar por chave ou descrição" value={search} onChange={(e) => setSearch(e.target.value)} />
          <label className="flex items-center gap-2 text-xs">
            <Checkbox checked={onlyCurrent} onChange={(e) => setOnlyCurrent(e.target.checked)} /> Somente vigentes hoje
          </label>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Chave</TableHead>
              <TableHead>Descrição</TableHead>
              <TableHead>Valor</TableHead>
              <TableHead>Versão</TableHead>
              <TableHead>Vigência</TableHead>
              <TableHead className="w-48 text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <LoadingRows cols={6} rows={3} />}
            {data?.results.map((p) => (
              <TableRow key={p.id}>
                <TableCell className="font-mono text-xs font-semibold">{p.key}</TableCell>
                <TableCell className="text-xs">{p.description || "—"}</TableCell>
                <TableCell className="max-w-[220px] truncate font-mono text-xs">{showValue(p.value)}</TableCell>
                <TableCell>v{p.version} {p.is_current && <Badge variant="success" className="ml-1">Vigente</Badge>}</TableCell>
                <TableCell className="text-xs tabular">{formatDate(p.valid_from)} a {p.valid_to ? formatDate(p.valid_to) : "indeterminado"}</TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setHistoryKey(p.key)}><History /> Histórico</Button>
                    {can("admin.parametros", "incluir") && (
                      <Button size="sm" variant="outline" onClick={() => setCreating({ key: p.key, description: p.description })}>Nova versão</Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={6} text="Nenhum parâmetro cadastrado." />}
          </TableBody>
        </Table>
      </Card>

      {creating && <ParameterDialog initial={creating} onClose={() => setCreating(null)} onSaved={() => mutate()} />}
      {historyKey && <HistoryDialog paramKey={historyKey} onClose={() => setHistoryKey(null)} />}
    </>
  );
}

function ParameterDialog({ initial, onClose, onSaved }: { initial: { key?: string; description?: string }; onClose: () => void; onSaved: () => void }) {
  const isNewVersion = Boolean(initial.key);
  const [form, setForm] = useState({
    key: initial.key ?? "",
    description: initial.description ?? "",
    value: "",
    valid_from: "",
    change_reason: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    let value: unknown = form.value;
    const trimmed = form.value.trim();
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        value = JSON.parse(trimmed);
      } catch {
        setErrors({ value: "JSON inválido." });
        return;
      }
    }
    setBusy(true);
    try {
      await api("parameters", { method: "POST", body: { ...form, value } });
      toast.success(isNewVersion ? "Nova versão registrada." : "Parâmetro cadastrado.");
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
            <DialogTitle>{isNewVersion ? `Nova versão de ${initial.key}` : "Novo parâmetro"}</DialogTitle>
            <DialogDescription>
              Valores monetários devem ser informados como texto decimal com ponto (ex.: 8157.41) — nunca como número de ponto flutuante.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <FormField label="Chave" htmlFor="key" required error={errors.key} hint="ex.: teto_rgps, aliquota.servidor">
              <Input id="key" value={form.key} disabled={isNewVersion} onChange={(e) => setForm({ ...form, key: e.target.value })} required />
            </FormField>
            <FormField label="Vigência inicial" htmlFor="valid_from" required error={errors.valid_from}>
              <Input id="valid_from" type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} required />
            </FormField>
            <FormField label="Descrição" htmlFor="description" error={errors.description} className="sm:col-span-2">
              <Input id="description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </FormField>
            <FormField label="Valor" htmlFor="value" required error={errors.value} className="sm:col-span-2" hint="Texto simples ou JSON (objetos e listas).">
              <Textarea id="value" className="font-mono" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} required />
            </FormField>
            {isNewVersion && (
              <FormField label="Motivo da alteração" htmlFor="reason" required error={errors.change_reason} className="sm:col-span-2" hint="Ex.: número da portaria ou lei.">
                <Textarea id="reason" value={form.change_reason} onChange={(e) => setForm({ ...form, change_reason: e.target.value })} required />
              </FormField>
            )}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Registrar</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function HistoryDialog({ paramKey, onClose }: { paramKey: string; onClose: () => void }) {
  const { data } = useSWR<Paginated<Parameter>>(`parameters${qs({ key: paramKey, page_size: 100 })}`, fetcher);
  const [open, setOpen] = useState(true);
  useEffect(() => { if (!open) onClose(); }, [open, onClose]);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Histórico de versões · <span className="font-mono">{paramKey}</span></DialogTitle>
        </DialogHeader>
        <DialogBody className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Versão</TableHead>
                <TableHead>Valor</TableHead>
                <TableHead>Vigência</TableHead>
                <TableHead>Motivo</TableHead>
                <TableHead>Registrado por</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.results.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>v{p.version}</TableCell>
                  <TableCell className="max-w-[200px] truncate font-mono text-xs">{showValue(p.value)}</TableCell>
                  <TableCell className="text-xs tabular">{formatDate(p.valid_from)} a {p.valid_to ? formatDate(p.valid_to) : "indeterminado"}</TableCell>
                  <TableCell className="text-xs">{p.change_reason || "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.created_by_name || "Sistema"}<div className="text-2xs">{formatDateTime(p.created_at)}</div></TableCell>
                </TableRow>
              ))}
              {data && data.results.length === 0 && <EmptyRow cols={5} />}
            </TableBody>
          </Table>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
