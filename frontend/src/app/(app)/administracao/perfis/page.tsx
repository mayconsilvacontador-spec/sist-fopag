"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { KeySquare, Loader2, Lock, Pencil, Plus, Trash2 } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
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
import { ApiError, api, fetcher, type Paginated } from "@/lib/api";
import type { Role } from "@/lib/types";

export default function RolesPage() {
  return (
    <RequirePermission module="admin.perfis">
      <Roles />
    </RequirePermission>
  );
}

function Roles() {
  const { can, me } = useSession();
  const { data, error, isLoading, mutate } = useSWR<Paginated<Role>>("roles?page_size=100", fetcher);
  const [editing, setEditing] = useState<Role | "new" | null>(null);
  const [removing, setRemoving] = useState<Role | null>(null);
  const isMaster = Boolean(me?.user.is_master);

  return (
    <>
      <PageHeader
        title="Perfis"
        description="Perfis de sistema são compartilhados por todas as instituições; perfis da instituição podem ser criados livremente."
        breadcrumb={[{ label: "Administração" }, { label: "Perfis" }]}
        actions={can("admin.perfis", "incluir") && (
          <Button onClick={() => setEditing("new")}><Plus /> Novo perfil</Button>
        )}
      />
      <Card>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Código</TableHead>
              <TableHead>Nome</TableHead>
              <TableHead>Abrangência</TableHead>
              <TableHead className="text-right">Permissões</TableHead>
              <TableHead className="text-right">Usuários</TableHead>
              <TableHead>Situação</TableHead>
              <TableHead className="w-48 text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <LoadingRows cols={7} />}
            {data?.results.map((r) => {
              const editable = can("admin.perfis", "editar") && (!r.is_system || isMaster);
              return (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs font-semibold">
                    <span className="inline-flex items-center gap-1">
                      {r.is_system && <Lock className="h-3 w-3 text-muted-foreground" aria-label="Perfil de sistema" />}
                      {r.code}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{r.name}</div>
                    {r.description && <div className="text-2xs text-muted-foreground">{r.description}</div>}
                  </TableCell>
                  <TableCell><Badge variant={r.is_system ? "info" : "neutral"}>{r.scope}</Badge></TableCell>
                  <TableCell className="text-right tabular">{r.permission_count}</TableCell>
                  <TableCell className="text-right tabular">{r.user_count}</TableCell>
                  <TableCell>{r.active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      {can("admin.permissoes") && (
                        <Button variant="outline" size="sm" asChild>
                          <Link href={`/administracao/permissoes?perfil=${r.id}`}><KeySquare /> Permissões</Link>
                        </Button>
                      )}
                      {editable && (
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(r)} aria-label="Editar"><Pencil /></Button>
                      )}
                      {!r.is_system && can("admin.perfis", "excluir") && (
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setRemoving(r)} aria-label="Excluir"><Trash2 /></Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
            {data && data.results.length === 0 && <EmptyRow cols={7} />}
          </TableBody>
        </Table>
      </Card>

      {editing && <RoleDialog role={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => mutate()} />}
      {removing && (
        <ConfirmDialog
          open
          onOpenChange={(v) => !v && setRemoving(null)}
          title="Excluir perfil"
          description={<>Excluir o perfil <strong>{removing.name}</strong>? Perfis atribuídos a usuários não podem ser excluídos.</>}
          confirmLabel="Excluir"
          destructive
          onConfirm={async () => {
            try {
              await api(`roles/${removing.id}`, { method: "DELETE" });
              toast.success("Perfil excluído.");
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

function RoleDialog({ role, onClose, onSaved }: { role: Role | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    code: role?.code ?? "",
    name: role?.name ?? "",
    description: role?.description ?? "",
    active: role?.active ?? true,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (role) await api(`roles/${role.id}`, { method: "PATCH", body: form });
      else await api("roles", { method: "POST", body: form });
      toast.success("Perfil salvo.");
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
          <DialogHeader>
            <DialogTitle>{role ? "Editar perfil" : "Novo perfil"}</DialogTitle>
            <DialogDescription>Após salvar, defina as permissões na matriz de permissões.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <FormField label="Código" htmlFor="code" required error={errors.code}>
              <Input id="code" value={form.code} disabled={role?.is_system} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required />
            </FormField>
            <FormField label="Nome" htmlFor="name" required error={errors.name}>
              <Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </FormField>
            <FormField label="Descrição" htmlFor="description" error={errors.description}>
              <Textarea id="description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </FormField>
            <label className="flex items-center gap-2 text-xs">
              <Checkbox checked={form.active} disabled={role?.code === "MASTER"} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Perfil ativo
            </label>
            {errors.non_field_errors && <p className="text-2xs text-destructive">{errors.non_field_errors}</p>}
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
