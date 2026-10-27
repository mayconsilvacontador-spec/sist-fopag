"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CalendarPlus, Loader2, Pencil, Plus } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { FormDialog } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox, Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api, fetcher, type Paginated } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { HOLIDAY_KIND } from "@/lib/options";
import type { ProcessTypeRow, Sector, UserRow } from "@/lib/types";

export default function ProtocolConfigPage() {
  return (
    <RequirePermission module="protocolo.configuracao">
      <Config />
    </RequirePermission>
  );
}

function Config() {
  const { can } = useSession();
  const canEdit = can("protocolo.configuracao", "editar");
  const canCreate = can("protocolo.configuracao", "incluir");
  return (
    <>
      <PageHeader
        title="Configuração do Protocolo"
        description="Setores (e quem trabalha em cada um), tipos de processo com seus prazos e feriados usados na contagem."
        breadcrumb={[{ label: "Protocolo" }, { label: "Configuração" }]}
      />
      <Card>
        <CardContent className="p-4">
          <Tabs defaultValue="setores">
            <TabsList>
              <TabsTrigger value="setores">Setores</TabsTrigger>
              <TabsTrigger value="tipos">Tipos de processo</TabsTrigger>
              <TabsTrigger value="feriados">Feriados</TabsTrigger>
            </TabsList>
            <TabsContent value="setores"><Sectors canEdit={canEdit} canCreate={canCreate} /></TabsContent>
            <TabsContent value="tipos"><Types canEdit={canEdit} canCreate={canCreate} /></TabsContent>
            <TabsContent value="feriados"><Holidays canEdit={canEdit} canCreate={canCreate} /></TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </>
  );
}

// ---------------------------------------------------------------------------- Setores
function Sectors({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
  const { data, isLoading, mutate } = useSWR<Paginated<Sector>>("protocol/sectors?page_size=200", fetcher);
  const [editing, setEditing] = useState<Sector | "new" | null>(null);
  return (
    <>
      <div className="mb-2 flex justify-end">{canCreate && <Button size="sm" onClick={() => setEditing("new")}><Plus /> Novo setor</Button>}</div>
      <Table>
        <TableHeader><TableRow><TableHead>Sigla</TableHead><TableHead>Setor</TableHead><TableHead>Servidores do setor</TableHead><TableHead>Situação</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={5} rows={2} />}
          {data?.results.map((s) => (
            <TableRow key={s.id}>
              <TableCell className="font-mono text-xs font-semibold">{s.code}</TableCell>
              <TableCell>{s.name}{s.organ_name && <div className="text-2xs text-muted-foreground">{s.organ_name}</div>}</TableCell>
              <TableCell className="text-xs">{s.member_names.length ? s.member_names.join(", ") : <span className="text-warning">Nenhum — ninguém poderá movimentar processos aqui</span>}</TableCell>
              <TableCell>{s.active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}</TableCell>
              <TableCell>{canEdit && <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(s)} aria-label="Editar"><Pencil /></Button>}</TableCell>
            </TableRow>
          ))}
          {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum setor. Crie o primeiro (ex.: PROT - Protocolo Geral) e inclua-se nele." />}
        </TableBody>
      </Table>
      {editing && <SectorDialog sector={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => mutate()} />}
    </>
  );
}

function SectorDialog({ sector, onClose, onSaved }: { sector: Sector | null; onClose: () => void; onSaved: () => void }) {
  const users = useSWR<Paginated<UserRow>>("users?status=ativos&page_size=200", fetcher);
  const [f, setF] = useState({ code: sector?.code ?? "", name: sector?.name ?? "", active: sector?.active ?? true });
  const [members, setMembers] = useState<string[]>(sector?.members ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { ...f, members };
      if (sector) await api(`protocol/sectors/${sector.id}`, { method: "PATCH", body });
      else await api("protocol/sectors", { method: "POST", body });
      toast.success("Setor salvo.");
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
            <DialogTitle>{sector ? `Setor ${sector.code}` : "Novo setor"}</DialogTitle>
            <DialogDescription>Somente os servidores do setor (ou o gestor do protocolo) recebem e movimentam processos nele.</DialogDescription>
          </DialogHeader>
          <DialogBody className="grid gap-3 sm:grid-cols-3">
            <FormField label="Sigla" htmlFor="s-code" required error={errors.code}>
              <Input id="s-code" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} required maxLength={20} />
            </FormField>
            <FormField label="Nome" htmlFor="s-name" required error={errors.name} className="sm:col-span-2">
              <Input id="s-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
            </FormField>
            <div className="sm:col-span-3">
              <div className="section-label mb-1.5">Servidores do setor</div>
              <div className="grid max-h-60 gap-1.5 overflow-auto rounded-md border p-3 sm:grid-cols-2">
                {!users.data && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                {users.data?.results.map((u) => (
                  <label key={u.id} className="flex items-center gap-2 text-xs">
                    <Checkbox checked={members.includes(u.id)}
                      onChange={(e) => setMembers((m) => (e.target.checked ? [...m, u.id] : m.filter((i) => i !== u.id)))} />
                    {u.full_name} <span className="text-muted-foreground">({u.username})</span>
                  </label>
                ))}
              </div>
              {errors.members && <p className="mt-1 text-2xs text-destructive">{errors.members}</p>}
            </div>
            {sector && (
              <label className="flex items-center gap-2 text-xs"><Checkbox checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Ativo</label>
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

// ---------------------------------------------------------------------------- Tipos de processo
function Types({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
  const { data, isLoading, mutate } = useSWR<Paginated<ProcessTypeRow>>("protocol/process-types?page_size=200", fetcher);
  const [editing, setEditing] = useState<ProcessTypeRow | "new" | null>(null);
  return (
    <>
      <div className="mb-2 flex justify-end">{canCreate && <Button size="sm" onClick={() => setEditing("new")}><Plus /> Novo tipo</Button>}</div>
      <Table>
        <TableHeader><TableRow><TableHead>Tipo de processo</TableHead><TableHead>Prazo</TableHead><TableHead>Prazo por setor</TableHead><TableHead>Situação</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={5} rows={2} />}
          {data?.results.map((t) => (
            <TableRow key={t.id}>
              <TableCell><div className="font-medium">{t.name}</div>{t.description && <div className="text-2xs text-muted-foreground">{t.description}</div>}</TableCell>
              <TableCell>{t.deadline_days} dia(s) {t.business_days ? "úteis" : "corridos"}</TableCell>
              <TableCell>{t.sector_deadline_days ? `${t.sector_deadline_days} dia(s)` : "—"}</TableCell>
              <TableCell>{t.active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}</TableCell>
              <TableCell>{canEdit && <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(t)} aria-label="Editar"><Pencil /></Button>}</TableCell>
            </TableRow>
          ))}
          {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum tipo. Ex.: Aposentadoria, Pensão por morte, Revisão de benefício, Certidão de tempo." />}
        </TableBody>
      </Table>
      {editing && (
        <FormDialog
          title={editing === "new" ? "Novo tipo de processo" : editing.name}
          fields={[
            { name: "name", label: "Nome", required: true, wide: true },
            { name: "deadline_days", label: "Prazo para conclusão (dias)", type: "number", required: true },
            { name: "sector_deadline_days", label: "Prazo por setor (dias)", type: "number", hint: "Opcional." },
            { name: "business_days", label: "Contar em dias úteis", type: "checkbox" },
            ...(editing !== "new" ? [{ name: "active", label: "Ativo", type: "checkbox" as const }] : []),
            { name: "description", label: "Descrição / documentos exigidos", type: "textarea" },
          ]}
          initial={editing === "new" ? { deadline_days: 30, business_days: true } : (editing as unknown as Record<string, unknown>)}
          onClose={() => setEditing(null)}
          submit={async (body) => {
            if (editing === "new") await api("protocol/process-types", { method: "POST", body });
            else await api(`protocol/process-types/${editing.id}`, { method: "PATCH", body });
            toast.success("Tipo salvo.");
            mutate();
          }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------- Feriados
type HolidayRow = { id: string; date: string; name: string; kind: string; kind_display: string; active: boolean };

function Holidays({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const { data, isLoading, mutate } = useSWR<HolidayRow[]>(`protocol/holidays?ano=${year}`, fetcher);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    setBusy(true);
    try {
      const r = await api<{ criados: number }>("protocol/holidays/generate", { method: "POST", body: { year } });
      toast.success(r.criados ? `${r.criados} feriado(s) incluído(s).` : "Os feriados nacionais do ano já estavam cadastrados.");
      mutate();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (h: HolidayRow) => {
    await api(`protocol/holidays/${h.id}`, { method: "PATCH", body: { active: !h.active } }).catch((e) => toast.error((e as Error).message));
    mutate();
  };

  return (
    <>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Select className="w-28" value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Ano">
          {[year - 1, year, year + 1].map((y) => <option key={y} value={y}>{y}</option>)}
        </Select>
        {canCreate && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={generate} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <CalendarPlus />} Incluir feriados nacionais de {year}</Button>
            <Button size="sm" onClick={() => setAdding(true)}><Plus /> Feriado estadual / municipal</Button>
          </div>
        )}
      </div>
      <Table>
        <TableHeader><TableRow><TableHead>Data</TableHead><TableHead>Descrição</TableHead><TableHead>Tipo</TableHead><TableHead>Na contagem de prazos</TableHead></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={4} rows={3} />}
          {data?.map((h) => (
            <TableRow key={h.id} className={h.active ? "" : "opacity-60"}>
              <TableCell className="tabular">{formatDate(h.date)}</TableCell>
              <TableCell>{h.name}</TableCell>
              <TableCell><Badge variant={h.kind === "PONTO_FACULTATIVO" ? "warning" : "default"}>{h.kind_display}</Badge></TableCell>
              <TableCell>
                <label className="flex items-center gap-2 text-xs">
                  <Checkbox checked={h.active} disabled={!canEdit} onChange={() => toggle(h)} /> {h.active ? "Dia não útil" : "Desconsiderado"}
                </label>
              </TableCell>
            </TableRow>
          ))}
          {data?.length === 0 && <EmptyRow cols={4} text="Nenhum feriado cadastrado neste ano. Use o botão para incluir os nacionais." />}
        </TableBody>
      </Table>
      <p className="pt-2 text-2xs text-muted-foreground">
        Inclua também os feriados estaduais (RJ: 23/04 São Jorge) e municipais. Pontos facultativos (Carnaval, Corpus Christi)
        vêm marcados como não úteis; desmarque se o órgão funcionar nesses dias.
      </p>
      {adding && (
        <FormDialog
          title="Novo feriado"
          fields={[
            { name: "date", label: "Data", type: "date", required: true },
            { name: "kind", label: "Tipo", type: "select", required: true, options: HOLIDAY_KIND },
            { name: "name", label: "Descrição", required: true, wide: true },
          ]}
          initial={{ kind: "MUNICIPAL" }}
          onClose={() => setAdding(false)}
          submit={async (body) => { await api("protocol/holidays", { method: "POST", body }); toast.success("Feriado incluído."); mutate(); }}
        />
      )}
    </>
  );
}
