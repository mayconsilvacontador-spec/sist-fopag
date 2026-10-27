"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Pencil, Plus, Save } from "lucide-react";

import { BrandingSection } from "@/components/admin/branding-section";
import { LifePurchaseSection } from "@/components/admin/life-purchase-section";
import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox, Input, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher, type Paginated } from "@/lib/api";
import { formatDate, maskCEP, maskCNPJ } from "@/lib/format";
import { INSTITUTION_KIND } from "@/lib/options";
import type { Plan } from "@/lib/types";

type Institution = {
  id: string; name: string; short_name: string; cnpj: string | null; cnpj_formatado: string;
  ente_name: string; ente_cnpj: string; address: string; district: string; city: string; uf: string;
  cep: string; phone: string; email: string; website: string; ibge_code: string; life_purchase_enabled: boolean;
  kind: string; has_coat_of_arms?: boolean; has_background?: boolean; background_intensity?: number;
};

const UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");

export default function InstitutionPage() {
  return (
    <RequirePermission module="admin.instituicao">
      <InstitutionScreen />
    </RequirePermission>
  );
}

function InstitutionScreen() {
  const { can, reload } = useSession();
  const canEdit = can("admin.instituicao", "editar");
  const { data, error, mutate } = useSWR<Institution>("institution/current", fetcher);
  const [form, setForm] = useState<Institution | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (data) setForm({ ...data, cnpj: data.cnpj ? maskCNPJ(data.cnpj) : "", ente_cnpj: data.ente_cnpj ? maskCNPJ(data.ente_cnpj) : "", cep: maskCEP(data.cep || "") });
  }, [data]);

  const set = (k: keyof Institution, mask?: (v: string) => string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => (f ? { ...f, [k]: mask ? mask(e.target.value) : e.target.value } : f));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setBusy(true);
    setErrors({});
    try {
      const { id: _id, cnpj_formatado: _c, life_purchase_enabled: _l, ...body } = form;
      void _id; void _c; void _l;
      await api("institution/current", { method: "PATCH", body: { ...body, cnpj: body.cnpj || null } });
      toast.success("Dados da instituição atualizados.");
      mutate();
      reload();
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Instituição"
        description="Dados cadastrais do RPPS e planos de custeio (segregação de massas)."
        breadcrumb={[{ label: "Administração" }, { label: "Instituição" }]}
      />
      {error && <ErrorState error={error} />}
      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader><CardTitle>Dados cadastrais</CardTitle></CardHeader>
          {form ? (
            <form onSubmit={save}>
              <CardContent className="grid gap-3 sm:grid-cols-6">
                <FormField label="Tipo de órgão" htmlFor="kind" required error={errors.kind} className="sm:col-span-6"
                  hint="Define os módulos disponíveis. Módulos previdenciários (concessão, folha de benefícios, atuarial) só aparecem para RPPS.">
                  <Select id="kind" value={form.kind} onChange={set("kind")} disabled={!canEdit}>
                    {INSTITUTION_KIND.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </Select>
                </FormField>
                <FormField label="Razão social" htmlFor="name" required error={errors.name} className="sm:col-span-6">
                  <Input id="name" value={form.name} onChange={set("name")} disabled={!canEdit} required />
                </FormField>
                <FormField label="Sigla" htmlFor="short_name" required error={errors.short_name} className="sm:col-span-2">
                  <Input id="short_name" value={form.short_name} onChange={set("short_name")} disabled={!canEdit} required />
                </FormField>
                <FormField label="CNPJ" htmlFor="cnpj" error={errors.cnpj} className="sm:col-span-2">
                  <Input id="cnpj" value={form.cnpj ?? ""} onChange={set("cnpj", maskCNPJ)} disabled={!canEdit} placeholder="00.000.000/0000-00" />
                </FormField>
                <FormField label="Telefone" htmlFor="phone" error={errors.phone} className="sm:col-span-2">
                  <Input id="phone" value={form.phone} onChange={set("phone")} disabled={!canEdit} />
                </FormField>
                <FormField label="Ente federativo" htmlFor="ente_name" error={errors.ente_name} className="sm:col-span-4">
                  <Input id="ente_name" value={form.ente_name} onChange={set("ente_name")} disabled={!canEdit} />
                </FormField>
                <FormField label="CNPJ do ente" htmlFor="ente_cnpj" error={errors.ente_cnpj} className="sm:col-span-2">
                  <Input id="ente_cnpj" value={form.ente_cnpj} onChange={set("ente_cnpj", maskCNPJ)} disabled={!canEdit} placeholder="00.000.000/0000-00" />
                </FormField>
                <FormField label="Código IBGE do ente" htmlFor="ibge_code" error={errors.ibge_code} className="sm:col-span-2" hint="7 dígitos — usado na base atuarial.">
                  <Input id="ibge_code" value={form.ibge_code} onChange={set("ibge_code", (v) => v.replace(/\D/g, "").slice(0, 7))} disabled={!canEdit} inputMode="numeric" />
                </FormField>
                <FormField label="Endereço" htmlFor="address" error={errors.address} className="sm:col-span-4">
                  <Input id="address" value={form.address} onChange={set("address")} disabled={!canEdit} />
                </FormField>
                <FormField label="Bairro" htmlFor="district" error={errors.district} className="sm:col-span-2">
                  <Input id="district" value={form.district} onChange={set("district")} disabled={!canEdit} />
                </FormField>
                <FormField label="Cidade" htmlFor="city" error={errors.city} className="sm:col-span-3">
                  <Input id="city" value={form.city} onChange={set("city")} disabled={!canEdit} />
                </FormField>
                <FormField label="UF" htmlFor="uf" error={errors.uf} className="sm:col-span-1">
                  <Select id="uf" value={form.uf} onChange={set("uf")} disabled={!canEdit}>
                    <option value="">—</option>
                    {UFS.map((u) => <option key={u} value={u}>{u}</option>)}
                  </Select>
                </FormField>
                <FormField label="CEP" htmlFor="cep" error={errors.cep} className="sm:col-span-2">
                  <Input id="cep" value={form.cep} onChange={set("cep", maskCEP)} disabled={!canEdit} placeholder="00000-000" />
                </FormField>
                <FormField label="E-mail" htmlFor="email" error={errors.email} className="sm:col-span-3">
                  <Input id="email" type="email" value={form.email} onChange={set("email")} disabled={!canEdit} />
                </FormField>
                <FormField label="Site" htmlFor="website" error={errors.website} className="sm:col-span-3">
                  <Input id="website" value={form.website} onChange={set("website")} disabled={!canEdit} placeholder="https://" />
                </FormField>
              </CardContent>
              {canEdit && (
                <div className="flex justify-end border-t bg-muted/40 px-4 py-2.5">
                  <Button type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Save />} Salvar</Button>
                </div>
              )}
            </form>
          ) : (
            <CardContent><div className="h-64 animate-pulse rounded bg-muted" /></CardContent>
          )}
        </Card>
        {data && <BrandingSection shortName={data.short_name} intensity={data.background_intensity ?? 15} canEdit={canEdit} onChanged={() => mutate()} />}
        <Plans canEdit={canEdit} canCreate={can("admin.instituicao", "incluir")} />
        {data && data.kind === "RPPS" && (
          <LifePurchaseSection
            enabled={data.life_purchase_enabled}
            canEdit={canEdit}
            canCreate={can("admin.instituicao", "incluir")}
            onChanged={() => { mutate(); reload(); }}
          />
        )}
      </div>
    </>
  );
}

function Plans({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
  const { data, isLoading, mutate } = useSWR<Paginated<Plan>>("plans?page_size=50", fetcher);
  const [editing, setEditing] = useState<Plan | "new" | null>(null);

  return (
    <Card className="self-start xl:col-span-2">
      <CardHeader>
        <CardTitle>Planos — segregação de massas</CardTitle>
        {canCreate && <Button size="sm" variant="outline" onClick={() => setEditing("new")}><Plus /> Novo plano</Button>}
      </CardHeader>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Código</TableHead>
            <TableHead>Plano</TableHead>
            <TableHead>Tipo</TableHead>
            <TableHead>Situação</TableHead>
            <TableHead className="w-10" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={5} rows={2} />}
          {data?.results.map((p) => (
            <TableRow key={p.id}>
              <TableCell className="font-mono text-xs font-semibold">{p.code}</TableCell>
              <TableCell>
                <div className="font-medium">{p.name}</div>
                {p.start_date && <div className="text-2xs text-muted-foreground">Desde {formatDate(p.start_date)}</div>}
              </TableCell>
              <TableCell><Badge variant={p.kind === "FINANCEIRO" ? "info" : "default"}>{p.kind_display}</Badge></TableCell>
              <TableCell>{p.active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}</TableCell>
              <TableCell>
                {canEdit && <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(p)} aria-label="Editar"><Pencil /></Button>}
              </TableCell>
            </TableRow>
          ))}
          {data && data.results.length === 0 && <EmptyRow cols={5} text="Nenhum plano cadastrado." />}
        </TableBody>
      </Table>
      <p className="border-t px-4 py-2.5 text-2xs text-muted-foreground">
        Todo beneficiário, receita, despesa e lançamento das próximas fases será obrigatoriamente vinculado a um plano.
        Planos não são excluídos — apenas inativados.
      </p>
      {editing && <PlanDialog plan={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => mutate()} />}
    </Card>
  );
}

function PlanDialog({ plan, onClose, onSaved }: { plan: Plan | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    code: plan?.code ?? "", name: plan?.name ?? "", kind: plan?.kind ?? "PREVIDENCIARIO",
    description: plan?.description ?? "", legal_basis: plan?.legal_basis ?? "",
    start_date: plan?.start_date ?? "", active: plan?.active ?? true,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { ...form, start_date: form.start_date || null };
      if (plan) await api(`plans/${plan.id}`, { method: "PATCH", body });
      else await api("plans", { method: "POST", body });
      toast.success("Plano salvo.");
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
            <DialogTitle>{plan ? "Editar plano" : "Novo plano"}</DialogTitle>
            <DialogDescription>Alterações são registradas na auditoria.</DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-2">
            <FormField label="Código" htmlFor="p-code" required error={errors.code}>
              <Input id="p-code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required />
            </FormField>
            <FormField label="Tipo" htmlFor="p-kind" required error={errors.kind}>
              <Select id="p-kind" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as Plan["kind"] })}>
                <option value="FINANCEIRO">Plano Financeiro</option>
                <option value="PREVIDENCIARIO">Plano Previdenciário</option>
              </Select>
            </FormField>
            <FormField label="Nome" htmlFor="p-name" required error={errors.name} className="sm:col-span-2">
              <Input id="p-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </FormField>
            <FormField label="Fundamento legal" htmlFor="p-legal" error={errors.legal_basis} className="sm:col-span-2" hint="Ex.: lei municipal que instituiu a segregação.">
              <Input id="p-legal" value={form.legal_basis} onChange={(e) => setForm({ ...form, legal_basis: e.target.value })} />
            </FormField>
            <FormField label="Início da segregação" htmlFor="p-start" error={errors.start_date}>
              <Input id="p-start" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            </FormField>
            <label className="flex items-center gap-2 self-end pb-2 text-xs">
              <Checkbox checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Plano ativo
            </label>
            <FormField label="Descrição" htmlFor="p-desc" error={errors.description} className="sm:col-span-2">
              <Textarea id="p-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
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
