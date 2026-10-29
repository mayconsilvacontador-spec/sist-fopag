"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { CheckCircle2, ClipboardCheck, Loader2, PlayCircle, Plus, RefreshCw, Search, Undo2, UserCheck } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { FilePick, RecadForm, useRecadState, type RecadData } from "./form";

type Stats = { total: number; PENDENTE: number; ENVIADO: number; DEVOLVIDO: number; APROVADO: number; atrasados: number; percentual: number };
type Campaign = {
  id: string; name: string; legal_act: string; act_date: string | null; start_date: string; end_date: string; audience: string;
  audience_display: string; organ: string | null; organ_name: string; portal_enabled: boolean; require_residence_proof: boolean;
  instructions: string; status: "RASCUNHO" | "ABERTA" | "ENCERRADA"; status_display: string; stats: Stats;
};
type Change = { grupo: string; campo: string; rotulo: string; antes: string; depois: string };
type Item = {
  id: string; campaign: string; campaign_name: string; person_name: string; person_cpf: string; phone: string; group: "SERVIDOR" | "BENEFICIARIO";
  group_display: string; due_date: string; status: string; status_display: string; channel_display: string; submitted_at: string | null;
  declarations: Record<string, string | boolean>; review_note: string; reviewed_by_name: string; reviewed_at: string | null;
  staff_followup: string; mudancas: Change[]; has_residence: boolean; has_id: boolean;
};
const VARIANT: Record<string, "default" | "info" | "success" | "warning" | "neutral" | "critical"> = {
  RASCUNHO: "neutral", ABERTA: "info", ENCERRADA: "success", PENDENTE: "warning", ENVIADO: "info", DEVOLVIDO: "critical", APROVADO: "success",
};

function StatsBar({ s }: { s: Stats }) {
  const pct = (n: number) => (s.total ? (100 * n) / s.total : 0);
  return (
    <div className="space-y-1.5">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
        <div className="bg-success" style={{ width: `${pct(s.APROVADO)}%` }} />
        <div className="bg-info" style={{ width: `${pct(s.ENVIADO)}%` }} />
        <div className="bg-critical" style={{ width: `${pct(s.DEVOLVIDO)}%` }} />
      </div>
      <div className="flex flex-wrap gap-x-3 text-2xs text-muted-foreground">
        <span><b className="text-success">{s.APROVADO}</b> aprovados</span><span><b className="text-info">{s.ENVIADO}</b> a conferir</span>
        <span><b className="text-critical">{s.DEVOLVIDO}</b> devolvidos</span><span><b className="text-warning">{s.PENDENTE}</b> pendentes</span>
        <span>· {s.percentual}% concluído</span>
      </div>
    </div>
  );
}

// ============================================================ Campanhas
export function RecadCampaignsPage() {
  return <RequirePermission module="recadastramento.campanhas"><Campaigns /></RequirePermission>;
}

function Campaigns() {
  const { can } = useSession();
  const router = useRouter();
  const sel = useSearchParams().get("c");
  const { data, error, mutate } = useSWR<Paginated<Campaign>>("recadastramento/campanhas?page_size=100", fetcher);
  const organs = useSWR<Paginated<{ id: string; name: string }>>("organs?page_size=200", fetcher);
  const [editing, setEditing] = useState<Campaign | "new" | null>(null);
  const current = data?.results.find((c) => c.id === sel) ?? data?.results[0];
  const act = async (c: Campaign, path: string, ok: string) => {
    try {
      const r = await api<{ incluidos?: number }>(`recadastramento/campanhas/${c.id}/${path}`, { method: "POST", body: {} });
      toast.success(r.incluidos !== undefined ? `${ok} ${r.incluidos} pessoa(s) incluída(s).` : ok);
      mutate();
    } catch (err) { toast.error((err as Error).message); }
  };
  const fields: FieldDef[] = [
    { name: "name", label: "Nome da campanha", required: true, wide: true },
    { name: "legal_act", label: "Ato que determinou", required: true, hint: "Ex.: Decreto nº 123/2026" },
    { name: "act_date", label: "Data do ato", type: "date" },
    { name: "start_date", label: "Início", type: "date", required: true },
    { name: "end_date", label: "Fim (prazo)", type: "date", required: true },
    { name: "audience", label: "Quem participa", type: "select", required: true, options: [{ value: "TODOS", label: "Servidores, aposentados e pensionistas" }, { value: "SERVIDORES", label: "Só servidores ativos" }, { value: "BENEFICIARIOS", label: "Só aposentados e pensionistas" }] },
    { name: "organ", label: "Só servidores do órgão (opcional)", type: "select", options: [{ value: "", label: "Todos os órgãos" }, ...(organs.data?.results ?? []).map((o) => ({ value: o.id, label: o.name }))] },
    { name: "instructions", label: "Orientações (aparecem no Portal)", type: "textarea", wide: true },
    { name: "portal_enabled", label: "Permitir recadastramento pelo Portal do Segurado", type: "checkbox" },
    { name: "require_residence_proof", label: "Exigir comprovante de residência", type: "checkbox" },
  ];
  const year = new Date().getFullYear();
  return (
    <>
      <PageHeader title="Campanhas de Recadastramento" description="Cada campanha segue o ato do órgão. O segurado atualiza os dados pelo Portal ou no atendimento; a equipe confere antes de gravar no cadastro."
        breadcrumb={[{ label: "Recadastramento" }, { label: "Campanhas" }]}
        actions={can("recadastramento.campanhas", "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Nova campanha</Button>} />
      {error && <ErrorState error={error} />}
      <div className="grid gap-4 xl:grid-cols-12">
        <Card className="self-start xl:col-span-5">
          <CardHeader><CardTitle>Campanhas</CardTitle></CardHeader>
          <div className="divide-y">
            {data?.results.map((c) => (
              <button key={c.id} type="button" onClick={() => router.replace(`?c=${c.id}`)}
                className={cn("block w-full space-y-2 px-4 py-3 text-left hover:bg-muted/50", current?.id === c.id && "bg-primary-soft")}>
                <div className="flex items-start justify-between gap-2">
                  <div><div className="text-[13.5px] font-semibold text-primary-strong">{c.name}</div>
                    <div className="text-2xs text-muted-foreground">{c.legal_act} · {formatDate(c.start_date)} a {formatDate(c.end_date)}</div></div>
                  <Badge variant={VARIANT[c.status]}>{c.status_display}</Badge>
                </div>
                {c.status !== "RASCUNHO" && <StatsBar s={c.stats} />}
              </button>
            ))}
            {data && data.results.length === 0 && <div className="px-4 py-8 text-center text-xs text-muted-foreground">Nenhuma campanha ainda.</div>}
          </div>
        </Card>
        {current && (
          <Card className="self-start xl:col-span-7">
            <CardHeader><CardTitle>{current.name}</CardTitle><Badge variant={VARIANT[current.status]}>{current.status_display}</Badge></CardHeader>
            <CardContent className="space-y-4 text-xs">
              <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                <div><span className="text-muted-foreground">Ato: </span>{current.legal_act}{current.act_date ? ` de ${formatDate(current.act_date)}` : ""}</div>
                <div><span className="text-muted-foreground">Período: </span>{formatDate(current.start_date)} a {formatDate(current.end_date)}</div>
                <div><span className="text-muted-foreground">Participam: </span>{current.audience_display}{current.organ_name ? ` · ${current.organ_name}` : ""}</div>
                <div><span className="text-muted-foreground">Portal: </span>{current.portal_enabled ? "sim" : "não"} · comprovante {current.require_residence_proof ? "exigido" : "opcional"}</div>
              </div>
              {current.status !== "RASCUNHO" && <StatsBar s={current.stats} />}
              <div className="flex flex-wrap gap-2">
                {current.status === "RASCUNHO" && can("recadastramento.campanhas", "editar") && <>
                  <Button size="sm" variant="outline" onClick={() => setEditing(current)}>Editar</Button>
                  <Button size="sm" onClick={() => act(current, "open", "Campanha aberta.")}><PlayCircle /> Abrir campanha</Button>
                </>}
                {current.status === "ABERTA" && <>
                  {can("recadastramento.campanhas", "editar") && <Button size="sm" variant="outline" onClick={() => act(current, "refresh", "Lista atualizada.")}><RefreshCw /> Incluir novas pessoas</Button>}
                  {can("recadastramento.campanhas", "editar") && <Button size="sm" variant="outline" onClick={() => setEditing(current)}>Prorrogar / orientações</Button>}
                  {can("recadastramento.campanhas", "fechar") && <Button size="sm" variant="ghost" onClick={() => act(current, "close", "Campanha encerrada.")}>Encerrar campanha</Button>}
                </>}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
      {editing && (
        <FormDialog title={editing === "new" ? "Nova campanha de recadastramento" : "Editar campanha"}
          fields={editing !== "new" && editing.status === "ABERTA" ? fields.filter((f) => ["end_date", "instructions", "portal_enabled"].includes(f.name)) : fields}
          initial={editing === "new" ? { start_date: `${year}-01-01`, end_date: `${year}-03-31`, audience: "TODOS", organ: "", portal_enabled: true, require_residence_proof: true }
            : { ...editing, act_date: editing.act_date ?? "", organ: editing.organ ?? "" }}
          onClose={() => setEditing(null)}
          submit={async (body) => {
            const payload = { ...body, act_date: body.act_date || null, organ: body.organ || null };
            if (editing === "new") await api("recadastramento/campanhas", { method: "POST", body: payload });
            else await api(`recadastramento/campanhas/${editing.id}`, { method: "PATCH", body: payload });
            toast.success("Campanha salva.");
            setEditing(null);
            mutate();
          }} />
      )}
    </>
  );
}

// ============================================================ Segurados / Beneficiários
const GROUPS = {
  segurados: { group: "SERVIDOR", module: "recadastramento.segurados", title: "Recadastramento de Servidores", description: "Servidores ativos: confira os envios do Portal ou registre o atendimento presencial." },
  beneficiarios: { group: "BENEFICIARIO", module: "recadastramento.beneficiarios", title: "Recadastramento de Aposentados e Pensionistas", description: "Confira os envios do Portal ou registre o atendimento presencial." },
} as const;

export function RecadItemsPage({ kind }: { kind: keyof typeof GROUPS }) {
  return <RequirePermission module={GROUPS[kind].module}><Items kind={kind} /></RequirePermission>;
}

function Items({ kind }: { kind: keyof typeof GROUPS }) {
  const cfg = GROUPS[kind];
  const { can } = useSession();
  const camps = useSWR<Paginated<Campaign>>("recadastramento/campanhas?page_size=100", fetcher);
  const [camp, setCamp] = useState("");
  const [status, setStatus] = useState("ENVIADO");
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => { const t = setTimeout(() => { setTerm(search); setPage(1); }, 300); return () => clearTimeout(t); }, [search]);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Item>>(
    `recadastramento/itens${qs({ grupo: cfg.group, situacao: status || undefined, campanha: camp || undefined, search: term || undefined, page })}`, fetcher, { keepPreviousData: true });
  const [reviewing, setReviewing] = useState<Item | null>(null);
  const [presential, setPresential] = useState<Item | null>(null);
  const canReview = can(cfg.module, "aprovar");
  return (
    <>
      <PageHeader title={cfg.title} description={cfg.description} breadcrumb={[{ label: "Recadastramento" }, { label: cfg.title }]} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <Select className="w-56" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
            <option value="ENVIADO">A conferir (enviados)</option><option value="PENDENTE,DEVOLVIDO">Pendentes e devolvidos</option>
            <option value="APROVADO">Aprovados</option><option value="">Todos</option>
          </Select>
          <Select className="w-56" value={camp} onChange={(e) => { setCamp(e.target.value); setPage(1); }} aria-label="Campanha">
            <option value="">Todas as campanhas</option>{camps.data?.results.filter((c) => c.status !== "RASCUNHO").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <div className="relative w-60"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-8" placeholder="Nome ou CPF" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
          {data && <span className="ml-auto text-xs text-muted-foreground">{data.count} registro(s)</span>}
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Pessoa</TableHead><TableHead>Campanha</TableHead><TableHead>Prazo</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={5} />}
            {data?.results.map((i) => (
              <TableRow key={i.id}>
                <TableCell><div className="font-medium">{i.person_name}</div><div className="text-2xs text-muted-foreground">{i.person_cpf}{i.phone ? ` · ${i.phone}` : ""}</div></TableCell>
                <TableCell className="text-xs">{i.campaign_name}</TableCell>
                <TableCell>{formatDate(i.due_date)}</TableCell>
                <TableCell><Badge variant={VARIANT[i.status]}>{i.status_display}</Badge>
                  {i.submitted_at && <div className="text-2xs text-muted-foreground">{i.channel_display} · {formatDateTime(i.submitted_at)}</div>}
                  {i.staff_followup && <div className="text-2xs text-warning">Tem providência para a equipe</div>}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    {(i.status === "ENVIADO" || i.status === "APROVADO") && <Button size="sm" variant={i.status === "ENVIADO" ? "default" : "outline"} onClick={() => setReviewing(i)}><ClipboardCheck /> {i.status === "ENVIADO" ? "Conferir" : "Ver"}</Button>}
                    {canReview && i.status !== "APROVADO" && <Button size="sm" variant="outline" onClick={() => setPresential(i)}><UserCheck /> Presencial</Button>}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum registro." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {reviewing && <ReviewDialog item={reviewing} canReview={canReview} onClose={() => setReviewing(null)} onDone={() => { setReviewing(null); mutate(); }} />}
      {presential && <PresentialDialog item={presential} onClose={() => setPresential(null)} onDone={() => { setPresential(null); mutate(); }} />}
    </>
  );
}

const DECL_LABEL: Record<string, string> = {
  acumula_cargo: "Declara acumulação de cargo", acumula_cargo_descricao: "Cargo acumulado", outro_beneficio: "Recebe outro benefício",
  outro_beneficio_descricao: "Outro benefício", dependentes_alteracoes: "Mudança nos dependentes", conta_alteracao: "Troca de conta",
};

function ReviewDialog({ item, canReview, onClose, onDone }: { item: Item; canReview: boolean; onClose: () => void; onDone: () => void }) {
  const [mode, setMode] = useState<"view" | "back">("view");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (path: string, body: object, ok: string) => {
    setBusy(true);
    try { await api(`recadastramento/itens/${item.id}/${path}?grupo=${item.group}`, { method: "POST", body }); toast.success(ok); onDone(); }
    catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  const file = (tipo: string) => `/api/backend/recadastramento/itens/${item.id}/file?tipo=${tipo}&grupo=${item.group}`;
  const decl = Object.entries(item.declarations).filter(([k, v]) => k !== "veracidade" && v && DECL_LABEL[k]);
  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{item.status === "ENVIADO" ? "Conferir recadastramento" : "Recadastramento aprovado"}</DialogTitle>
          <DialogDescription>{item.person_name} · {item.person_cpf} · {item.group_display} · {item.channel_display} {item.submitted_at ? `em ${formatDateTime(item.submitted_at)}` : ""}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4 text-xs">
          <div>
            <div className="mb-1 font-semibold">O que muda no cadastro</div>
            {item.mudancas.length ? (
              <Table>
                <TableHeader><TableRow><TableHead>Campo</TableHead><TableHead>Hoje no cadastro</TableHead><TableHead>Informado</TableHead></TableRow></TableHeader>
                <TableBody>{item.mudancas.map((m) => (
                  <TableRow key={m.grupo + m.campo}><TableCell className="font-medium">{m.rotulo}</TableCell>
                    <TableCell className="text-muted-foreground line-through">{String(m.antes || "—")}</TableCell><TableCell className="font-semibold text-primary-strong">{String(m.depois || "—")}</TableCell></TableRow>
                ))}</TableBody>
              </Table>
            ) : <p className="text-muted-foreground">Nenhuma alteração: o segurado confirmou os dados atuais.</p>}
          </div>
          {decl.length > 0 && (
            <div className="rounded-lg border border-warning-border bg-warning-soft p-3">
              <div className="mb-1 font-semibold text-warning">Declarações que pedem providência</div>
              {decl.map(([k, v]) => <div key={k}><b>{DECL_LABEL[k]}:</b> {v === true ? "sim" : String(v)}</div>)}
              <div className="mt-1 text-muted-foreground">Dependentes e conta bancária não são alterados por aqui: trate na Pasta do Servidor com os documentos.</div>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {item.has_residence && <a href={file("comprovante")} target="_blank" rel="noreferrer"><Button size="sm" variant="outline">Ver comprovante de residência</Button></a>}
            {item.has_id && <a href={file("documento")} target="_blank" rel="noreferrer"><Button size="sm" variant="outline">Ver documento</Button></a>}
          </div>
          {item.status === "APROVADO" && <p className="text-muted-foreground">Aprovado por {item.reviewed_by_name} em {item.reviewed_at ? formatDateTime(item.reviewed_at) : "—"}.</p>}
          {mode === "back" && <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="O que o segurado precisa corrigir? (ex.: comprovante ilegível ou antigo)" />}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Fechar</Button>
          {item.status === "ENVIADO" && canReview && (mode === "view" ? <>
            <Button variant="outline" className="text-critical" onClick={() => setMode("back")}><Undo2 /> Devolver</Button>
            <Button onClick={() => run("approve", {}, "Aprovado. Cadastro atualizado.")} disabled={busy}>{busy && <Loader2 className="animate-spin" />}<CheckCircle2 /> Aprovar e atualizar cadastro</Button>
          </> : <Button variant="destructive" disabled={busy || reason.trim().length < 10} onClick={() => run("give-back", { reason }, "Devolvido. O segurado foi avisado.")}>Devolver ao segurado</Button>)}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PresentialDialog({ item, onClose, onDone }: { item: Item; onClose: () => void; onDone: () => void }) {
  const { data: cad } = useSWR<RecadData>(`recadastramento/itens/${item.id}/cadastro?grupo=${item.group}`, fetcher);
  return cad ? <PresentialForm item={item} cad={cad} onClose={onClose} onDone={onDone} /> : null;
}

function PresentialForm({ item, cad, onClose, onDone }: { item: Item; cad: RecadData; onClose: () => void; onDone: () => void }) {
  const st = useRecadState(cad);
  const [comp, setComp] = useState<File | null>(null);
  const [doc, setDoc] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("dados", JSON.stringify(st.data));
      fd.append("declaracoes", JSON.stringify({ ...st.decl, veracidade: true }));
      if (comp) fd.append("comprovante", comp);
      if (doc) fd.append("documento", doc);
      const res = await fetch(`/api/backend/recadastramento/itens/${item.id}/presential?grupo=${item.group}`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Falha ao registrar.");
      toast.success("Recadastramento presencial registrado e aprovado.");
      onDone();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Atendimento presencial — {item.person_name}</DialogTitle>
          <DialogDescription>Confira cada dado com o segurado e os documentos originais. Ao salvar, o recadastramento é aprovado e o cadastro é atualizado.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <RecadForm data={st.data} setData={st.setData} decl={st.decl} setDecl={st.setDecl} />
          <FilePick label="Comprovante de residência (digitalizado)" file={comp} setFile={setComp} />
          <FilePick label="Documento de identidade (opcional)" file={doc} setFile={setDoc} />
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button onClick={submit} disabled={busy}>{busy && <Loader2 className="animate-spin" />} Salvar e aprovar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
