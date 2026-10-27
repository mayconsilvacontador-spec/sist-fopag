"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { KeyRound, Loader2, ShieldAlert } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function ProfilePage() {
  const { me } = useSession();
  const params = useSearchParams();
  const forced = params.get("trocar") === "1" || me?.user.must_change_password;

  const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.new_password !== form.confirm) {
      setErrors({ confirm: "As senhas não conferem." });
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      await api("auth/change-password", {
        method: "POST",
        body: { current_password: form.current_password, new_password: form.new_password },
      });
      toast.success("Senha alterada. Por segurança, entre novamente.");
      await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
      window.location.assign("/login");
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Meu perfil" breadcrumb={[{ label: "Usuário" }, { label: "Meu perfil" }]} />
      {forced && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-warning-border bg-warning-soft px-3 py-2.5 text-xs text-warning">
          <ShieldAlert className="h-4 w-4 shrink-0" />
          <span>É necessário definir uma nova senha antes de utilizar o sistema.</span>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Dados do usuário</CardTitle></CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-[13px]">
              <dt className="text-muted-foreground">Nome</dt><dd className="font-medium">{me?.user.full_name}</dd>
              <dt className="text-muted-foreground">Login</dt><dd className="font-mono text-xs">{me?.user.username}</dd>
              <dt className="text-muted-foreground">CPF</dt><dd>{me?.user.cpf || "—"}</dd>
              <dt className="text-muted-foreground">E-mail</dt><dd>{me?.user.email || "—"}</dd>
              <dt className="text-muted-foreground">Instituição</dt><dd>{me?.institution?.name}</dd>
              <dt className="text-muted-foreground">Perfis</dt>
              <dd className="flex flex-wrap gap-1">{me?.roles.map((r) => <Badge key={r.id}>{r.code}</Badge>)}</dd>
              <dt className="text-muted-foreground">Último acesso</dt><dd>{formatDateTime(me?.user.last_login)}</dd>
              <dt className="text-muted-foreground">Permissões</dt><dd>{me?.permissions.length}</dd>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Alterar senha</CardTitle></CardHeader>
          <form onSubmit={submit}>
            <CardContent className="space-y-3">
              <FormField label="Senha atual" htmlFor="cur" required error={errors.current_password}>
                <Input id="cur" type="password" autoComplete="current-password" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} required />
              </FormField>
              <FormField label="Nova senha" htmlFor="new" required error={errors.new_password} hint="Mínimo de 10 caracteres; evite senhas comuns ou só numéricas.">
                <Input id="new" type="password" autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} required minLength={10} />
              </FormField>
              <FormField label="Confirme a nova senha" htmlFor="conf" required error={errors.confirm}>
                <Input id="conf" type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} required />
              </FormField>
              <p className="text-2xs text-muted-foreground">Ao alterar a senha, todas as sessões abertas são encerradas.</p>
            </CardContent>
            <div className="flex justify-end border-t bg-muted/40 px-4 py-2.5">
              <Button type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <KeyRound />} Alterar senha</Button>
            </div>
          </form>
        </Card>
      </div>
    </>
  );
}
