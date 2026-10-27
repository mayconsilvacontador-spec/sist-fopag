"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Info, Loader2, Lock, RotateCcw, Save } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { ErrorState } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox, Label, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import type { ModuleInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

type Matrix = {
  groups: { code: string; name: string }[];
  actions: { code: string; name: string }[];
  modules: ModuleInfo[];
  roles: { id: string; code: string; name: string; is_system: boolean; is_master: boolean; permissions: string[] }[];
};

export default function PermissionsPage() {
  return (
    <RequirePermission module="admin.permissoes">
      <Permissions />
    </RequirePermission>
  );
}

function Permissions() {
  const router = useRouter();
  const params = useSearchParams();
  const { can, me } = useSession();
  const { data, error, mutate } = useSWR<Matrix>("permissions/matrix", fetcher);
  const roleId = params.get("perfil") || data?.roles.find((r) => !r.is_master)?.id || data?.roles[0]?.id;
  const role = data?.roles.find((r) => r.id === roleId);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSelected(new Set(role?.permissions ?? []));
  }, [role]);

  const readOnly =
    !can("admin.permissoes", "editar") || !role || role.is_master || (role.is_system && !me?.user.is_master);

  const original = useMemo(() => new Set(role?.permissions ?? []), [role]);
  const added = [...selected].filter((k) => !original.has(k));
  const removed = [...original].filter((k) => !selected.has(k));
  const dirty = added.length + removed.length > 0;

  const toggle = (key: string, on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      if (on) n.add(key);
      else n.delete(key);
      return n;
    });

  const toggleRow = (m: ModuleInfo, on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      m.actions.forEach((a) => (on ? n.add(`${m.code}:${a}`) : n.delete(`${m.code}:${a}`)));
      return n;
    });

  const save = async () => {
    if (!role) return;
    setSaving(true);
    try {
      await api(`roles/${role.id}/permissions`, { method: "PUT", body: { permissions: [...selected] } });
      toast.success("Permissões atualizadas e registradas na auditoria.");
      await mutate();
    } catch (e) {
      toast.error((e as Error).message);
      throw e;
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Permissões"
        description="Controle por módulo e por ação. A validação é feita no servidor em cada operação."
        breadcrumb={[{ label: "Administração" }, { label: "Permissões" }]}
        actions={
          !readOnly && (
            <>
              <Button variant="outline" size="sm" disabled={!dirty || saving} onClick={() => setSelected(new Set(original))}>
                <RotateCcw /> Descartar
              </Button>
              <Button size="sm" disabled={!dirty || saving} onClick={() => setConfirming(true)}>
                {saving ? <Loader2 className="animate-spin" /> : <Save />} Salvar alterações
              </Button>
            </>
          )
        }
      />

      {error && <ErrorState error={error} />}

      <Card className="mb-3 flex flex-wrap items-center gap-3 px-4 py-2.5">
        <Label htmlFor="perfil">Perfil</Label>
        <Select
          id="perfil"
          className="w-72"
          value={roleId ?? ""}
          onChange={(e) => {
            if (dirty && !window.confirm("Descartar as alterações não salvas?")) return;
            router.replace(`/administracao/permissoes?perfil=${e.target.value}`);
          }}
        >
          {data?.roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name} ({r.code}){r.is_system ? " · sistema" : ""}
            </option>
          ))}
        </Select>
        {role && <span className="text-xs text-muted-foreground">{selected.size} permissões selecionadas</span>}
        {dirty && <Badge variant="warning">{added.length} a conceder · {removed.length} a revogar</Badge>}
        {role?.is_master && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><Lock className="h-3.5 w-3.5" /> O perfil MASTER possui todas as permissões e não pode ser alterado.</span>
        )}
        {role?.is_system && !role.is_master && !me?.user.is_master && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><Info className="h-3.5 w-3.5" /> Perfis de sistema só podem ser alterados por usuários MASTER.</span>
        )}
      </Card>

      {!data && !error && <Skeleton className="h-96 w-full" />}

      {data && role && (
        <Card className="overflow-hidden">
          <div className="max-h-[calc(100vh-260px)] overflow-auto thin-scroll">
            <table className="w-full text-[13px]">
              <thead className="sticky top-0 z-10 bg-muted">
                <tr>
                  <th className="border-b px-3 py-2 text-left text-2xs font-semibold uppercase tracking-wider text-muted-foreground">Módulo / tela</th>
                  {data.actions.map((a) => (
                    <th key={a.code} className="w-[84px] border-b px-1 py-2 text-center text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {a.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.groups.map((g) => {
                  const mods = data.modules.filter((m) => m.group === g.code);
                  if (!mods.length) return null;
                  return (
                    <GroupRows key={g.code} name={g.name} modules={mods} actions={data.actions} selected={selected} readOnly={readOnly} toggle={toggle} toggleRow={toggleRow} />
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Confirmar alteração de permissões"
        description={
          <>
            Perfil <strong>{role?.name}</strong>: {added.length} permissão(ões) concedida(s) e {removed.length} revogada(s).
            A alteração afeta todos os usuários com este perfil e será registrada na auditoria.
          </>
        }
        confirmLabel="Salvar"
        onConfirm={save}
      />
    </>
  );
}

function GroupRows({
  name, modules, actions, selected, readOnly, toggle, toggleRow,
}: {
  name: string;
  modules: ModuleInfo[];
  actions: { code: string; name: string }[];
  selected: Set<string>;
  readOnly: boolean;
  toggle: (key: string, on: boolean) => void;
  toggleRow: (m: ModuleInfo, on: boolean) => void;
}) {
  return (
    <>
      <tr>
        <td colSpan={actions.length + 1} className="border-b bg-primary-soft/60 px-3 py-1.5 text-2xs font-bold uppercase tracking-wider text-primary">
          {name}
        </td>
      </tr>
      {modules.map((m) => {
        const all = m.actions.every((a) => selected.has(`${m.code}:${a}`));
        return (
          <tr key={m.code} className="border-b hover:bg-muted/50">
            <td className="px-3 py-1.5">
              <label className={cn("flex items-center gap-2", !readOnly && "cursor-pointer")}>
                <Checkbox disabled={readOnly} checked={all} onChange={(e) => toggleRow(m, e.target.checked)} aria-label={`Todas as ações de ${m.name}`} />
                <span className="font-medium">{m.name}</span>
                {!m.implemented && <span className="text-2xs text-muted-foreground">{m.phase ? `Fase ${m.phase}` : "a definir"}</span>}
              </label>
            </td>
            {actions.map((a) => {
              const available = m.actions.includes(a.code);
              const key = `${m.code}:${a.code}`;
              return (
                <td key={a.code} className="px-1 py-1.5 text-center">
                  {available ? (
                    <Checkbox disabled={readOnly} checked={selected.has(key)} onChange={(e) => toggle(key, e.target.checked)} aria-label={`${m.name}: ${a.name}`} />
                  ) : (
                    <span className="text-muted-foreground/40">·</span>
                  )}
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}
