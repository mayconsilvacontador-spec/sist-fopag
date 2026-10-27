"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import {
  Copy, KeyRound, Loader2, LockOpen, MoreHorizontal, Pencil, Plus, Search, UserCheck, UserX,
} from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
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
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Checkbox, Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDateTime, isValidCPF, maskCPF } from "@/lib/format";
import type { Role, UserRow } from "@/lib/types";

export default function UsersPage() {
  return (
    <RequirePermission module="admin.usuarios">
      <Users />
    </RequirePermission>
  );
}

type Pending = { kind: "activate" | "deactivate" | "unlock" | "reset"; user: UserRow } | null;

function Users() {
  const { can, me } = useSession();
  const canCreate = can("admin.usuarios", "incluir");
  const canEdit = can("admin.usuarios", "editar");

  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState("ativos");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [tempPassword, setTempPassword] = useState<{ user: string; password: string } | null>(null);

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, error, isLoading, mutate } = useSWR<Paginated<UserRow>>(
    `users${qs({ search: debounced, status, page })}`,
    fetcher,
    { keepPreviousData: true },
  );

  const runAction = async () => {
    if (!pending) return;
    const { kind, user } = pending;
    try {
      if (kind === "reset") {
        const r = await api<{ temporary_password: string }>(`users/${user.id}/reset-password`, { method: "POST" });
        setTempPassword({ user: user.username, password: r.temporary_password });
      } else {
        await api(`users/${user.id}/${kind}`, { method: "POST" });
        toast.success("Operação realizada.");
      }
      mutate();
    } catch (e) {
      toast.error((e as Error).message);
      throw e;
    }
  };

  const confirmText: Record<string, { title: string; desc: string; label: string; destructive?: boolean }> = {
    activate: { title: "Ativar usuário", desc: "O usuário voltará a ter acesso ao sistema.", label: "Ativar" },
    deactivate: { title: "Inativar usuário", desc: "O acesso será bloqueado e as sessões abertas encerradas. O histórico é preservado.", label: "Inativar", destructive: true },
    unlock: { title: "Desbloquear usuário", desc: "Zera as tentativas de login falhas e remove o bloqueio temporário.", label: "Desbloquear" },
    reset: { title: "Redefinir senha", desc: "Uma senha temporária será gerada e exibida uma única vez. O usuário deverá trocá-la no próximo acesso.", label: "Gerar senha temporária" },
  };

  return (
    <>
      <PageHeader
        title="Usuários"
        description="Usuários com acesso à instituição. Usuários não são excluídos: são inativados, preservando a auditoria."
        breadcrumb={[{ label: "Administração" }, { label: "Usuários" }]}
        actions={canCreate && (
          <Button onClick={() => setEditing("new")}>
            <Plus /> Novo usuário
          </Button>
        )}
      />

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="relative w-full max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome, login, e-mail ou CPF" className="pl-8" />
          </div>
          <Select className="w-40" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
            <option value="ativos">Ativos</option>
            <option value="inativos">Inativos</option>
            <option value="bloqueados">Bloqueados</option>
            <option value="">Todos</option>
          </Select>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Login</TableHead>
              <TableHead>CPF</TableHead>
              <TableHead>Perfis</TableHead>
              <TableHead>Situação</TableHead>
              <TableHead>Último acesso</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={7} />}
            {data?.results.map((u) => (
              <TableRow key={u.id}>
                <TableCell>
                  <div className="font-medium">{u.full_name}</div>
                  <div className="text-2xs text-muted-foreground">{u.email || "—"}{u.job_title ? ` · ${u.job_title}` : ""}</div>
                </TableCell>
                <TableCell className="font-mono text-xs">{u.username}</TableCell>
                <TableCell className="tabular">{u.cpf_formatado || "—"}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {u.roles.length ? u.roles.map((r) => <Badge key={r.id} variant={r.code === "MASTER" ? "info" : "default"}>{r.code}</Badge>) : <Badge variant="warning">Sem perfil</Badge>}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {u.is_active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}
                    {u.is_locked && <Badge variant="critical">Bloqueado</Badge>}
                    {u.must_change_password && u.is_active && <Badge variant="warning">Trocar senha</Badge>}
                  </div>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {formatDateTime(u.last_login)}
                  {u.last_login_ip && <div className="text-2xs">IP {u.last_login_ip}</div>}
                </TableCell>
                <TableCell>
                  {canEdit && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Ações"><MoreHorizontal /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setEditing(u)}><Pencil /> Editar</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setPending({ kind: "reset", user: u })}><KeyRound /> Redefinir senha</DropdownMenuItem>
                        {u.is_locked && <DropdownMenuItem onSelect={() => setPending({ kind: "unlock", user: u })}><LockOpen /> Desbloquear</DropdownMenuItem>}
                        <DropdownMenuSeparator />
                        {u.is_active ? (
                          <DropdownMenuItem destructive disabled={u.id === me?.user.id} onSelect={() => setPending({ kind: "deactivate", user: u })}>
                            <UserX /> Inativar
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onSelect={() => setPending({ kind: "activate", user: u })}><UserCheck /> Ativar</DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={7} />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>

      {editing && (
        <UserDialog
          user={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(u) => {
            mutate();
            if (u.temporary_password) setTempPassword({ user: u.username, password: u.temporary_password });
          }}
        />
      )}

      {pending && (
        <ConfirmDialog
          open
          onOpenChange={(v) => !v && setPending(null)}
          title={confirmText[pending.kind].title}
          description={<><strong>{pending.user.full_name}</strong> ({pending.user.username}). {confirmText[pending.kind].desc}</>}
          confirmLabel={confirmText[pending.kind].label}
          destructive={confirmText[pending.kind].destructive}
          onConfirm={runAction}
        />
      )}

      <Dialog open={Boolean(tempPassword)} onOpenChange={(v) => !v && setTempPassword(null)}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Senha temporária</DialogTitle>
            <DialogDescription>
              Entregue ao usuário <strong>{tempPassword?.user}</strong> por meio seguro. Ela não será exibida novamente e
              deverá ser trocada no primeiro acesso.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <div className="flex items-center gap-2 rounded-md border bg-muted px-3 py-2">
              <code className="flex-1 select-all font-mono text-sm">{tempPassword?.password}</code>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  navigator.clipboard?.writeText(tempPassword?.password || "").then(
                    () => toast.success("Senha copiada."),
                    () => toast.error("Não foi possível copiar. Selecione e copie manualmente."),
                  );
                }}
              >
                <Copy /> Copiar
              </Button>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button onClick={() => setTempPassword(null)}>Concluir</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function UserDialog({
  user, onClose, onSaved,
}: {
  user: UserRow | null;
  onClose: () => void;
  onSaved: (u: UserRow) => void;
}) {
  const { data: roles } = useSWR<Paginated<Role>>("roles?page_size=100", fetcher);
  const [form, setForm] = useState({
    username: user?.username ?? "",
    full_name: user?.full_name ?? "",
    cpf: user?.cpf_formatado ?? "",
    email: user?.email ?? "",
    phone: user?.phone ?? "",
    job_title: user?.job_title ?? "",
  });
  const [roleIds, setRoleIds] = useState<string[]>(user?.roles.map((r) => r.id) ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: k === "cpf" ? maskCPF(e.target.value) : e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (form.cpf && !isValidCPF(form.cpf)) local.cpf = "CPF inválido.";
    if (form.full_name.trim().split(" ").length < 2) local.full_name = "Informe nome e sobrenome.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      const body = { ...form, cpf: form.cpf || null, role_ids: roleIds };
      const saved = user
        ? await api<UserRow>(`users/${user.id}`, { method: "PATCH", body })
        : await api<UserRow>("users", { method: "POST", body });
      toast.success(user ? "Usuário atualizado." : "Usuário criado.");
      onSaved(saved);
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
      <DialogContent size="lg">
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader>
            <DialogTitle>{user ? "Editar usuário" : "Novo usuário"}</DialogTitle>
            <DialogDescription>
              {user ? "Alterações cadastrais e de perfis são registradas na auditoria." : "Uma senha temporária será gerada automaticamente."}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <FormField label="Nome completo" htmlFor="full_name" required error={errors.full_name} className="sm:col-span-2">
              <Input id="full_name" value={form.full_name} onChange={set("full_name")} required />
            </FormField>
            <FormField label="Login" htmlFor="username" required error={errors.username} hint="Letras minúsculas, sem espaços.">
              <Input id="username" value={form.username} onChange={set("username")} required autoComplete="off" />
            </FormField>
            <FormField label="CPF" htmlFor="cpf" error={errors.cpf}>
              <Input id="cpf" value={form.cpf} onChange={set("cpf")} placeholder="000.000.000-00" inputMode="numeric" />
            </FormField>
            <FormField label="E-mail" htmlFor="email" error={errors.email}>
              <Input id="email" type="email" value={form.email} onChange={set("email")} />
            </FormField>
            <FormField label="Telefone" htmlFor="phone" error={errors.phone}>
              <Input id="phone" value={form.phone} onChange={set("phone")} />
            </FormField>
            <FormField label="Cargo/função" htmlFor="job_title" error={errors.job_title} className="sm:col-span-2">
              <Input id="job_title" value={form.job_title} onChange={set("job_title")} />
            </FormField>
            <div className="sm:col-span-2">
              <div className="section-label mb-1.5">Perfis de acesso nesta instituição</div>
              <div className="grid gap-1.5 rounded-md border p-3 sm:grid-cols-2">
                {roles?.results.filter((r) => r.active).map((r) => (
                  <label key={r.id} className="flex items-start gap-2 text-xs">
                    <Checkbox
                      className="mt-0.5"
                      checked={roleIds.includes(r.id)}
                      onChange={(e) =>
                        setRoleIds((ids) => (e.target.checked ? [...ids, r.id] : ids.filter((i) => i !== r.id)))
                      }
                    />
                    <span>
                      <span className="font-medium">{r.name}</span>{" "}
                      <span className="text-muted-foreground">({r.code})</span>
                      {r.description && <span className="block text-2xs text-muted-foreground">{r.description}</span>}
                    </span>
                  </label>
                ))}
                {!roles && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
              </div>
              {errors.role_ids && <p className="mt-1 text-2xs text-destructive">{errors.role_ids}</p>}
            </div>
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
