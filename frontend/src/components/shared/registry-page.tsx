"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Pencil, Plus, Search } from "lucide-react";

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
import { maskCNPJ } from "@/lib/format";

type Row = Record<string, unknown> & { id: string; active?: boolean };

export type FieldDef = {
  name: string;
  label: string;
  type?: "text" | "number" | "select" | "ref" | "checkbox" | "textarea" | "cnpj" | "digits" | "date" | "money" | "password";
  required?: boolean;
  options?: { value: string | number; label: string }[];
  /** type=ref: endpoint da lista e campo exibido */
  ref?: { endpoint: string; label: (r: Row) => string };
  maxLength?: number;
  hint?: string;
  wide?: boolean;
};

export type ColumnDef = { label: string; render: (r: Row) => React.ReactNode; className?: string };

export type RegistryConfig = {
  module: string;
  endpoint: string;
  title: string;
  singular: string;
  description: string;
  breadcrumb: string;
  searchPlaceholder: string;
  columns: ColumnDef[];
  fields: FieldDef[];
  defaults?: Record<string, unknown>;
};

/** Tela padrão de cadastro de referência: lista com busca, inclusão, edição e inativação (sem exclusão). */
export function RegistryPage({ config }: { config: RegistryConfig }) {
  return (
    <RequirePermission module={config.module}>
      <Registry config={config} />
    </RequirePermission>
  );
}

function Registry({ config }: { config: RegistryConfig }) {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [onlyActive, setOnlyActive] = useState(true);
  const [editing, setEditing] = useState<Row | "new" | null>(null);

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, error, isLoading, mutate } = useSWR<Paginated<Row>>(
    `${config.endpoint}${qs({ search: debounced, page, ativos: onlyActive ? 1 : undefined })}`,
    fetcher,
    { keepPreviousData: true },
  );
  const canEdit = can(config.module, "editar");
  const cols = config.columns.length + 2;

  return (
    <>
      <PageHeader
        title={config.title}
        description={config.description}
        breadcrumb={[{ label: config.breadcrumb }, { label: config.title }]}
        actions={can(config.module, "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Novo</Button>}
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="relative w-full max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={config.searchPlaceholder} className="pl-8" />
          </div>
          <label className="flex items-center gap-2 text-xs">
            <Checkbox checked={onlyActive} onChange={(e) => { setOnlyActive(e.target.checked); setPage(1); }} /> Somente ativos
          </label>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              {config.columns.map((c) => <TableHead key={c.label} className={c.className}>{c.label}</TableHead>)}
              <TableHead>Situação</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={cols} />}
            {data?.results.map((r) => (
              <TableRow key={r.id}>
                {config.columns.map((c) => <TableCell key={c.label} className={c.className}>{c.render(r)}</TableCell>)}
                <TableCell>{r.active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}</TableCell>
                <TableCell>
                  {canEdit && (
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(r)} aria-label="Editar"><Pencil /></Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={cols} />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {editing && (
        <RegistryDialog config={config} row={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => mutate()} />
      )}
    </>
  );
}

function initialValue(f: FieldDef, row: Row | null, defaults?: Record<string, unknown>) {
  const v = row ? row[f.name] : defaults?.[f.name];
  if (f.type === "checkbox") return v ?? false;
  if (f.type === "cnpj") return v ? maskCNPJ(String(v)) : "";
  return v ?? "";
}

function RegistryDialog({
  config, row, onClose, onSaved,
}: {
  config: RegistryConfig;
  row: Row | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<Record<string, unknown>>(() => {
    const out: Record<string, unknown> = { active: row?.active ?? true };
    for (const f of config.fields) out[f.name] = initialValue(f, row, config.defaults);
    return out;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      const body: Record<string, unknown> = { ...form };
      for (const f of config.fields) {
        if ((f.type === "number" || f.type === "ref" || f.type === "select") && body[f.name] === "") body[f.name] = null;
      }
      if (row) await api(`${config.endpoint}/${row.id}`, { method: "PATCH", body });
      else await api(config.endpoint, { method: "POST", body });
      toast.success(`${config.singular} salvo(a).`);
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
            <DialogTitle>{row ? `Editar ${config.singular.toLowerCase()}` : `Novo(a) ${config.singular.toLowerCase()}`}</DialogTitle>
            <DialogDescription>Registros não são excluídos — apenas inativados. Alterações ficam na auditoria.</DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            {config.fields.map((f) => (
              <FieldInput key={f.name} field={f} value={form[f.name]} error={errors[f.name]}
                onChange={(v) => setForm((s) => ({ ...s, [f.name]: v }))} />
            ))}
            {row && (
              <label className="flex items-center gap-2 text-xs sm:col-span-2">
                <Checkbox checked={Boolean(form.active)} onChange={(e) => setForm((s) => ({ ...s, active: e.target.checked }))} /> Ativo
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

/**
 * Diálogo de formulário genérico (inclusão/edição) a partir de FieldDef.
 * `submit` recebe o corpo já normalizado (vazio -> null em datas, números e listas).
 */
export function FormDialog({
  title, description, fields, initial, submitLabel = "Salvar", onClose, submit, size = "md",
}: {
  title: string;
  description?: string;
  fields: FieldDef[];
  initial?: Record<string, unknown>;
  submitLabel?: string;
  onClose: () => void;
  submit: (body: Record<string, unknown>) => Promise<void>;
  size?: "sm" | "md" | "lg";
}) {
  const [form, setForm] = useState<Record<string, unknown>>(() => {
    const out: Record<string, unknown> = {};
    for (const f of fields) out[f.name] = initial?.[f.name] ?? (f.type === "checkbox" ? false : "");
    return out;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      const body: Record<string, unknown> = { ...form };
      for (const f of fields) {
        if (["number", "ref", "select", "date", "money"].includes(f.type ?? "") && body[f.name] === "") body[f.name] = null;
        if (f.type === "money" && typeof body[f.name] === "string") {
          const v = String(body[f.name]).trim();
          body[f.name] = v.includes(",") ? v.replace(/\./g, "").replace(",", ".") : v;
        }
      }
      await submit(body);
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
      <DialogContent size={size}>
        <form onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            {fields.map((f) => (
              <FieldInput key={f.name} field={f} value={form[f.name]} error={errors[f.name]}
                onChange={(v) => setForm((s) => ({ ...s, [f.name]: v }))} />
            ))}
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />} {submitLabel}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function FieldInput({ field: f, value, error, onChange }: {
  field: FieldDef; value: unknown; error?: string; onChange: (v: unknown) => void;
}) {
  const id = `f-${f.name}`;
  const cls = f.wide || f.type === "textarea" ? "sm:col-span-2" : undefined;
  if (f.type === "checkbox") {
    return (
      <label className="flex items-center gap-2 self-end pb-2 text-xs">
        <Checkbox checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} /> {f.label}
      </label>
    );
  }
  let input: React.ReactNode;
  if (f.type === "select") {
    input = (
      <Select id={id} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} required={f.required}>
        {/* Obrigatório sem valor: mostra "Selecione…" (antes o navegador exibia a 1ª opção sem tê-la escolhido) */}
        {f.required ? <option value="" disabled>Selecione…</option> : <option value="">—</option>}
        {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </Select>
    );
  } else if (f.type === "ref" && f.ref) {
    input = <RefSelect id={id} field={f} value={String(value ?? "")} onChange={onChange} />;
  } else if (f.type === "textarea") {
    input = <Textarea id={id} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
  } else {
    input = (
      <Input
        id={id}
        type={f.type === "number" ? "number" : f.type === "date" ? "date" : f.type === "password" ? "password" : "text"}
        inputMode={f.type === "digits" || f.type === "cnpj" ? "numeric" : f.type === "money" ? "decimal" : undefined}
        value={String(value ?? "")}
        maxLength={f.maxLength}
        required={f.required}
        placeholder={f.type === "cnpj" ? "00.000.000/0000-00" : f.type === "money" ? "0,00" : undefined}
        onChange={(e) => {
          const v = e.target.value;
          onChange(f.type === "cnpj" ? maskCNPJ(v) : f.type === "digits" ? v.replace(/\D/g, "") : v);
        }}
      />
    );
  }
  return <FormField label={f.label} htmlFor={id} required={f.required} error={error} hint={f.hint} className={cls}>{input}</FormField>;
}

function RefSelect({ id, field, value, onChange }: { id: string; field: FieldDef; value: string; onChange: (v: unknown) => void }) {
  const { data } = useSWR<Paginated<Row>>(`${field.ref!.endpoint}?ativos=1&page_size=500`, fetcher);
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} required={field.required}>
      <option value="">{data ? "Selecione" : "Carregando..."}</option>
      {data?.results.map((r) => <option key={r.id} value={r.id}>{field.ref!.label(r)}</option>)}
    </Select>
  );
}
