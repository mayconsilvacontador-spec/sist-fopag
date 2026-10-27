"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { Ban, Camera, CheckCircle2, Download, Loader2, Lock, PlayCircle, Plus, RefreshCw, Search, ShieldAlert, Upload, XCircle } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
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
import { api, download, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type Stats = { total: number; PENDENTE: number; REALIZADA: number; BLOQUEADO: number; DISPENSADA: number; percentual: number; vencidas: number };
type Campaign = {
  id: string; name: string; kind: string; kind_display: string; legal_act: string; act_date: string | null;
  start_date: string; end_date: string; deadline_rule: string; deadline_rule_display: string; grace_days: number;
  audience: string; audience_display: string; segment: string; portal_notice: boolean; allow_portal: boolean; instructions: string;
  status: "RASCUNHO" | "ABERTA" | "ENCERRADA"; status_display: string; opened_at: string | null; stats: Stats;
};
type Proof = {
  id: string; campaign: string; campaign_name: string; person: string; person_name: string; person_cpf: string;
  birth_date: string | null; phone: string; due_date: string; status: string; status_display: string; done_date: string | null;
  channel: string; channel_display: string; notes: string; registered_by_name: string; has_attachment: boolean;
  suspended_at: string | null; days_late: number | null;
  portal_submitted_at: string | null; status_before_portal: string; review_note: string; has_portal_photos: boolean;
  portal_liveness: { desafios?: string[]; movimento?: number; camera?: string; fotos?: number; metodo?: string }; frames_count: number;
};

const CHANNELS = [
  ["PRESENCIAL", "Presencial no órgão"], ["VISITA", "Visita domiciliar / hospitalar"], ["PROCURADOR", "Por procurador / curador"],
  ["BANCO", "Na agência bancária (comprovante)"], ["PORTAL", "Pelo Portal do Segurado"], ["OUTRO", "Outro"],
];
const STATUS_VARIANT: Record<string, "default" | "info" | "success" | "warning" | "neutral" | "critical"> = {
  RASCUNHO: "neutral", ABERTA: "info", ENCERRADA: "success", PENDENTE: "warning", REALIZADA: "success",
  BLOQUEADO: "critical", DISPENSADA: "neutral", EM_ANALISE: "info",
};

/** Pede a senha (assinatura eletrônica) antes de um ato que mexe em benefício. */
function PasswordDialog({ title, summary, label, onConfirm, onClose, destructive }: {
  title: string; summary: React.ReactNode; label: string; onConfirm: (pw: string) => Promise<void>; onClose: () => void; destructive?: boolean;
}) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Lock className="h-4 w-4 text-primary" /> {title}</DialogTitle>
          <DialogDescription asChild><div>{summary}</div></DialogDescription>
        </DialogHeader>
        <DialogBody>
          <label className="space-y-1 text-xs"><span className="font-medium">Sua senha (assinatura eletrônica)</span>
            <Input type="password" autoFocus autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} /></label>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button variant={destructive ? "destructive" : "default"} disabled={!pw || busy}
            onClick={async () => { setBusy(true); try { await onConfirm(pw); onClose(); } catch { /* exibida */ } finally { setBusy(false); } }}>
            {busy && <Loader2 className="animate-spin" />} {label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function StatsBar({ s }: { s: Stats }) {
  const pct = (n: number) => (s.total ? (100 * n) / s.total : 0);
  return (
    <div className="space-y-1.5">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
        <div className="bg-success" style={{ width: `${pct(s.REALIZADA)}%` }} />
        <div className="bg-chart-4" style={{ width: `${pct(s.DISPENSADA)}%` }} />
        <div className="bg-critical" style={{ width: `${pct(s.BLOQUEADO)}%` }} />
      </div>
      <div className="flex flex-wrap gap-x-3 text-2xs text-muted-foreground">
        <span><b className="text-success">{s.REALIZADA}</b> realizadas</span><span><b>{s.DISPENSADA}</b> dispensadas</span>
        <span><b className="text-warning">{s.PENDENTE}</b> pendentes</span><span><b className="text-critical">{s.BLOQUEADO}</b> suspensos</span>
        <span>· {s.percentual}% concluído</span>
      </div>
    </div>
  );
}

// ============================================================ Campanhas
export function CampaignsPage() {
  return <RequirePermission module="provadevida.campanhas"><Campaigns /></RequirePermission>;
}

function Campaigns() {
  const { can } = useSession();
  const router = useRouter();
  const sel = useSearchParams().get("c");
  const { data, error, isLoading, mutate } = useSWR<Paginated<Campaign>>("provadevida/campanhas?page_size=100", fetcher);
  const [editing, setEditing] = useState<Campaign | "new" | null>(null);
  const [suspending, setSuspending] = useState<Campaign | null>(null);
  const current = data?.results.find((c) => c.id === sel) ?? data?.results[0];

  const act = async (c: Campaign, path: string, ok: string) => {
    try {
      const r = await api<Campaign & { incluidos?: number }>(`provadevida/campanhas/${c.id}/${path}`, { method: "POST", body: {} });
      toast.success(r.incluidos !== undefined ? `${ok} ${r.incluidos} beneficiário(s) incluído(s).` : ok);
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const fields: FieldDef[] = [
    { name: "name", label: "Nome da campanha", required: true, wide: true, maxLength: 150 },
    { name: "kind", label: "Tipo", type: "select", required: true, options: [{ value: "ANUAL", label: "Anual" }, { value: "SEMESTRAL", label: "Semestral" }, { value: "EXTRAORDINARIA", label: "Extraordinária (decreto/portaria)" }] },
    { name: "legal_act", label: "Ato que determinou", required: true, maxLength: 200, hint: "Ex.: Decreto nº 123/2026" },
    { name: "act_date", label: "Data do ato", type: "date" },
    { name: "start_date", label: "Início", type: "date", required: true },
    { name: "end_date", label: "Fim (prazo final)", type: "date", required: true },
    { name: "deadline_rule", label: "Prazo de cada beneficiário", type: "select", required: true, options: [{ value: "FIM_CAMPANHA", label: "Até o fim da campanha" }, { value: "MES_ANIVERSARIO", label: "Até o fim do mês de aniversário" }] },
    { name: "grace_days", label: "Tolerância antes da suspensão (dias)", type: "number", required: true },
    { name: "audience", label: "Quem participa", type: "select", required: true, options: [{ value: "TODOS", label: "Aposentados e pensionistas" }, { value: "APOSENTADOS", label: "Só aposentados" }, { value: "PENSIONISTAS", label: "Só pensionistas" }] },
    { name: "segment", label: "Folha", type: "select", options: [{ value: "", label: "Todas" }, { value: "FINANCEIRO", label: "Financeiro" }, { value: "PREVIDENCIARIO", label: "Previdenciário" }, { value: "COMPRA_VIDAS", label: "Compra de Vidas" }] },
    { name: "instructions", label: "Orientações ao beneficiário (aparecem no Portal)", type: "textarea", wide: true },
    { name: "portal_notice", label: "Avisar no Portal do Segurado (e preparar mensagem ao celular)", type: "checkbox" },
    { name: "allow_portal", label: "Aceitar prova de vida pelo Portal (selfie + documento, conferida pela equipe)", type: "checkbox" },
  ];
  const year = new Date().getFullYear();

  return (
    <>
      <PageHeader title="Campanhas de Prova de Vida" description="Cada campanha segue o ato do órgão (anual, semestral ou extraordinária por decreto), com prazo e regra de suspensão próprios."
        breadcrumb={[{ label: "Prova de Vida" }, { label: "Campanhas" }]}
        actions={can("provadevida.campanhas", "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Nova campanha</Button>} />
      {error && <ErrorState error={error} />}
      <div className="grid gap-4 xl:grid-cols-12">
        <Card className="self-start xl:col-span-5">
          <CardHeader><CardTitle>Campanhas</CardTitle></CardHeader>
          <div className="divide-y">
            {isLoading && <div className="p-4"><Loader2 className="h-4 w-4 animate-spin" /></div>}
            {data?.results.map((c) => (
              <button key={c.id} type="button" onClick={() => router.replace(`?c=${c.id}`)}
                className={cn("block w-full space-y-2 px-4 py-3 text-left hover:bg-muted/50", current?.id === c.id && "bg-primary-soft")}>
                <div className="flex items-start justify-between gap-2">
                  <div><div className="text-[13.5px] font-semibold text-primary-strong">{c.name}</div>
                    <div className="text-2xs text-muted-foreground">{c.legal_act} · {formatDate(c.start_date)} a {formatDate(c.end_date)}</div></div>
                  <Badge variant={STATUS_VARIANT[c.status]}>{c.status_display}</Badge>
                </div>
                {c.status !== "RASCUNHO" && <StatsBar s={c.stats} />}
              </button>
            ))}
            {data && data.results.length === 0 && <div className="px-4 py-8 text-center text-xs text-muted-foreground">Nenhuma campanha. Crie a primeira conforme o ato do órgão.</div>}
          </div>
        </Card>

        {current && (
          <Card className="self-start xl:col-span-7">
            <CardHeader><CardTitle>{current.name}</CardTitle><Badge variant={STATUS_VARIANT[current.status]}>{current.status_display}</Badge></CardHeader>
            <CardContent className="space-y-4 text-xs">
              <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                <div><span className="text-muted-foreground">Tipo: </span>{current.kind_display}</div>
                <div><span className="text-muted-foreground">Ato: </span>{current.legal_act}{current.act_date ? ` de ${formatDate(current.act_date)}` : ""}</div>
                <div><span className="text-muted-foreground">Período: </span>{formatDate(current.start_date)} a {formatDate(current.end_date)}</div>
                <div><span className="text-muted-foreground">Prazo: </span>{current.deadline_rule_display}</div>
                <div><span className="text-muted-foreground">Tolerância: </span>{current.grace_days} dia(s) após o prazo</div>
                <div><span className="text-muted-foreground">Participam: </span>{current.audience_display}{current.segment ? ` · folha ${current.segment.toLowerCase()}` : ""}</div>
                {current.instructions && <div className="sm:col-span-2"><span className="text-muted-foreground">Orientações: </span>{current.instructions}</div>}
              </div>
              {current.status !== "RASCUNHO" && <StatsBar s={current.stats} />}
              {current.stats.vencidas > 0 && (
                <div className="rounded-lg border border-warning-border bg-warning-soft px-3 py-2 text-warning">
                  <b>{current.stats.vencidas} beneficiário(s)</b> passaram do prazo e da tolerância sem prova de vida.
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {current.status === "RASCUNHO" && can("provadevida.campanhas", "editar") && <>
                  <Button size="sm" variant="outline" onClick={() => setEditing(current)}>Editar</Button>
                  <Button size="sm" onClick={() => act(current, "open", "Campanha aberta.")}><PlayCircle /> Abrir campanha</Button>
                </>}
                {current.status === "ABERTA" && <>
                  <Link href={`/prova-de-vida/pendentes?c=${current.id}`}><Button size="sm">Registrar provas</Button></Link>
                  {can("provadevida.campanhas", "editar") && <Button size="sm" variant="outline" onClick={() => act(current, "refresh", "Lista atualizada.")}><RefreshCw /> Incluir novos beneficiários</Button>}
                  {can("provadevida.campanhas", "editar") && <Button size="sm" variant="outline" onClick={() => setEditing(current)}>Prorrogar / orientações</Button>}
                  {can("provadevida.bloqueados", "aprovar") && current.stats.vencidas > 0 && (
                    <Button size="sm" variant="destructive" onClick={() => setSuspending(current)}><ShieldAlert /> Suspender {current.stats.vencidas} atrasado(s)</Button>)}
                  {can("provadevida.campanhas", "fechar") && <Button size="sm" variant="ghost" onClick={() => act(current, "close", "Campanha encerrada.")}>Encerrar campanha</Button>}
                </>}
              </div>
              <p className="text-2xs text-muted-foreground">A suspensão é feita só quando você mandar, com senha, e fica registrada no histórico de cada benefício. A prova feita depois restabelece o benefício.</p>
            </CardContent>
          </Card>
        )}
      </div>

      {editing && (
        <FormDialog title={editing === "new" ? "Nova campanha de prova de vida" : "Editar campanha"} fields={editing !== "new" && editing.status === "ABERTA"
          ? fields.filter((f) => ["end_date", "grace_days", "instructions", "portal_notice", "allow_portal"].includes(f.name)) : fields}
          initial={editing === "new" ? { kind: "ANUAL", start_date: `${year}-01-01`, end_date: `${year}-12-31`, deadline_rule: "MES_ANIVERSARIO", grace_days: 30, audience: "TODOS", segment: "", portal_notice: true, allow_portal: true }
            : { ...editing, act_date: editing.act_date ?? "" }}
          onClose={() => setEditing(null)}
          submit={async (body) => {
            const payload = { ...body, grace_days: Number(body.grace_days || 0), act_date: body.act_date || null };
            if (editing === "new") await api("provadevida/campanhas", { method: "POST", body: payload });
            else await api(`provadevida/campanhas/${editing.id}`, { method: "PATCH", body: payload });
            toast.success("Campanha salva.");
            setEditing(null);
            mutate();
          }} />
      )}
      {suspending && (
        <PasswordDialog title="Suspender benefícios" label="Suspender" destructive onClose={() => setSuspending(null)}
          summary={<>Os benefícios de <b>{suspending.stats.vencidas} beneficiário(s)</b> que não fizeram a prova até o prazo + {suspending.grace_days} dia(s) de tolerância serão suspensos ({suspending.legal_act}).</>}
          onConfirm={async (pw) => {
            try {
              const r = await api<{ pessoas: number; beneficios: number }>(`provadevida/campanhas/${suspending.id}/suspend`, { method: "POST", body: { password: pw } });
              toast.success(`${r.beneficios} benefício(s) suspenso(s) de ${r.pessoas} pessoa(s).`);
              mutate();
            } catch (err) { toast.error((err as Error).message); throw err; }
          }} />
      )}
    </>
  );
}

// ============================================================ Pendentes / Realizadas / Bloqueados
const PROOF_PAGES = {
  pendentes: { module: "provadevida.pendentes", title: "Provas pendentes", status: "EM_ANALISE,PENDENTE", description: "Beneficiários que ainda não fizeram a prova de vida — os envios pelo Portal aparecem primeiro, para conferência." },
  realizadas: { module: "provadevida.realizadas", title: "Provas realizadas", status: "REALIZADA,DISPENSADA", description: "Provas registradas (e dispensas justificadas), com forma e responsável." },
  bloqueados: { module: "provadevida.bloqueados", title: "Benefícios suspensos por falta de prova", status: "BLOQUEADO", description: "Ao registrar a prova, o benefício é restabelecido (com senha)." },
} as const;

export function ProofsPage({ kind }: { kind: keyof typeof PROOF_PAGES }) {
  const cfg = PROOF_PAGES[kind];
  return <RequirePermission module={cfg.module}><Proofs kind={kind} /></RequirePermission>;
}

function Proofs({ kind }: { kind: keyof typeof PROOF_PAGES }) {
  const cfg = PROOF_PAGES[kind];
  const { can } = useSession();
  const params = useSearchParams();
  const camps = useSWR<Paginated<Campaign>>("provadevida/campanhas?page_size=100", fetcher);
  const [camp, setCamp] = useState(params.get("c") ?? "");
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [late, setLate] = useState(false);
  const [page, setPage] = useState(1);
  useEffect(() => { const t = setTimeout(() => { setTerm(search); setPage(1); }, 300); return () => clearTimeout(t); }, [search]);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Proof>>(
    `provadevida/provas${qs({ situacao: cfg.status, campanha: camp || undefined, search: term || undefined, vencidas: late ? 1 : undefined, page })}`, fetcher, { keepPreviousData: true });
  const [registering, setRegistering] = useState<Proof | null>(null);
  const [waiving, setWaiving] = useState<Proof | null>(null);
  const [reviewing, setReviewing] = useState<Proof | null>(null);
  const canRegister = can("provadevida.realizadas", "incluir") && (kind !== "bloqueados" || can("provadevida.bloqueados", "aprovar"));

  return (
    <>
      <PageHeader title={cfg.title} description={cfg.description} breadcrumb={[{ label: "Prova de Vida" }, { label: cfg.title }]} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <Select className="w-64" value={camp} onChange={(e) => { setCamp(e.target.value); setPage(1); }} aria-label="Campanha">
            <option value="">Todas as campanhas</option>
            {camps.data?.results.filter((c) => c.status !== "RASCUNHO").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <div className="relative w-64">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-8" placeholder="Nome ou CPF" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          {kind === "pendentes" && <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={late} onChange={(e) => setLate(e.target.checked)} /> Só com prazo vencido</label>}
          {data && <span className="ml-auto text-xs text-muted-foreground">{data.count} registro(s)</span>}
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow>
            <TableHead>Beneficiário</TableHead><TableHead>Campanha</TableHead><TableHead>Prazo</TableHead>
            {kind === "realizadas" ? <><TableHead>Realizada</TableHead><TableHead>Forma</TableHead><TableHead>Registrada por</TableHead></>
              : <><TableHead>Situação</TableHead><TableHead>Telefone</TableHead></>}
            <TableHead />
          </TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={6} />}
            {data?.results.map((p) => (
              <TableRow key={p.id}>
                <TableCell><div className="font-medium">{p.person_name}</div><div className="text-2xs text-muted-foreground">{p.person_cpf}{p.birth_date ? ` · nasc. ${formatDate(p.birth_date)}` : ""}</div></TableCell>
                <TableCell className="text-xs">{p.campaign_name}</TableCell>
                <TableCell>{formatDate(p.due_date)}{p.days_late ? <div className="text-2xs text-critical">{p.days_late} dia(s) de atraso</div> : null}</TableCell>
                {kind === "realizadas" ? <>
                  <TableCell>{p.status === "DISPENSADA" ? <Badge variant="neutral">Dispensada</Badge> : formatDate(p.done_date)}</TableCell>
                  <TableCell className="text-xs">{p.status === "DISPENSADA" ? p.notes : p.channel_display}</TableCell>
                  <TableCell className="text-xs">{p.registered_by_name}</TableCell>
                </> : <>
                  <TableCell><Badge variant={STATUS_VARIANT[p.status]}>{p.status_display}</Badge>{p.suspended_at && <div className="text-2xs text-muted-foreground">desde {formatDate(p.suspended_at)}</div>}
                    {p.review_note && p.status !== "EM_ANALISE" && <div className="text-2xs text-warning">Envio recusado: {p.review_note}</div>}</TableCell>
                  <TableCell className="text-xs">{p.phone}</TableCell>
                </>}
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    {p.has_attachment && <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Comprovante"
                      onClick={() => download(`provadevida/provas/${p.id}/attachment`, "comprovante").catch((e) => toast.error((e as Error).message))}><Download /></Button>}
                    {p.status === "EM_ANALISE" && canRegister && <Button size="sm" onClick={() => setReviewing(p)}><Camera /> Conferir fotos</Button>}
                    {kind !== "realizadas" && p.status !== "EM_ANALISE" && canRegister && <Button size="sm" onClick={() => setRegistering(p)}><CheckCircle2 /> {kind === "bloqueados" ? "Registrar e restabelecer" : "Registrar prova"}</Button>}
                    {kind === "pendentes" && can("provadevida.pendentes", "editar") && <Button size="sm" variant="ghost" onClick={() => setWaiving(p)}><Ban /> Dispensar</Button>}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum registro." />}
          </TableBody>
        </Table>
        {data && data.num_pages > 1 && (
          <div className="flex items-center justify-end gap-2 border-t px-4 py-2 text-xs">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
            <span>Página {data.page} de {data.num_pages}</span>
            <Button size="sm" variant="outline" disabled={page >= data.num_pages} onClick={() => setPage(page + 1)}>Próxima</Button>
          </div>
        )}
      </Card>
      {registering && <RegisterDialog proof={registering} onClose={() => setRegistering(null)} onDone={() => { setRegistering(null); mutate(); }} />}
      {waiving && <WaiveDialog proof={waiving} onClose={() => setWaiving(null)} onDone={() => { setWaiving(null); mutate(); }} />}
      {reviewing && <ReviewDialog proof={reviewing} onClose={() => setReviewing(null)} onDone={() => { setReviewing(null); mutate(); }} />}
    </>
  );
}

function RegisterDialog({ proof, onClose, onDone }: { proof: Proof; onClose: () => void; onDone: () => void }) {
  const blocked = proof.status === "BLOQUEADO";
  const [f, setF] = useState({ done_date: new Date().toISOString().slice(0, 10), channel: "PRESENCIAL", notes: "", password: "" });
  const file = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      Object.entries(f).forEach(([k, v]) => fd.append(k, v));
      if (file.current?.files?.[0]) fd.append("file", file.current.files[0]);
      const res = await fetch(`/api/backend/provadevida/provas/${proof.id}/register`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || Object.values(body).flat().join(" ") || "Falha ao registrar.");
      toast.success(body.restabelecidos ? `Prova registrada. ${body.restabelecidos} benefício(s) restabelecido(s).` : "Prova de vida registrada.");
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Registrar prova de vida</DialogTitle>
          <DialogDescription>{proof.person_name} · {proof.person_cpf}{blocked ? " — o benefício suspenso será restabelecido." : ""}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3 text-xs">
          <label className="block space-y-1"><span className="font-medium">Data da prova</span>
            <Input type="date" value={f.done_date} onChange={(e) => setF({ ...f, done_date: e.target.value })} /></label>
          <label className="block space-y-1"><span className="font-medium">Forma</span>
            <Select value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>{CHANNELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></label>
          <label className="block space-y-1"><span className="font-medium">Observações</span>
            <Textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="Ex.: atestado de vida apresentado pelo curador" /></label>
          <div className="space-y-1"><span className="font-medium">Comprovante (opcional — PDF, JPG ou PNG)</span>
            <input ref={file} type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden" onChange={(e) => setName(e.target.files?.[0]?.name ?? "")} />
            <div className="flex items-center gap-2"><Button size="sm" variant="outline" onClick={() => file.current?.click()}><Upload /> Escolher arquivo</Button><span className="truncate text-muted-foreground">{name}</span></div></div>
          {blocked && <label className="block space-y-1"><span className="font-medium">Sua senha (restabelecimento do benefício)</span>
            <Input type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button onClick={submit} disabled={busy || (blocked && !f.password)}>{busy && <Loader2 className="animate-spin" />} Registrar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function WaiveDialog({ proof, onClose, onDone }: { proof: Proof; onClose: () => void; onDone: () => void }) {
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent size="sm">
        <DialogHeader><DialogTitle>Dispensar prova de vida</DialogTitle>
          <DialogDescription>{proof.person_name}. Use só com fundamento (ex.: decisão judicial, prova feita em outro órgão conveniado).</DialogDescription></DialogHeader>
        <DialogBody><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Justificativa (mínimo de 15 caracteres)" /></DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button disabled={busy || notes.trim().length < 15} onClick={async () => {
            setBusy(true);
            try { await api(`provadevida/provas/${proof.id}/waive`, { method: "POST", body: { notes } }); toast.success("Dispensa registrada."); onDone(); }
            catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
          }}>{busy && <Loader2 className="animate-spin" />} Dispensar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


/** Conferência da prova enviada pelo Portal: selfie com documento + foto do documento. */
function ReviewDialog({ proof, onClose, onDone }: { proof: Proof; onClose: () => void; onDone: () => void }) {
  const blocked = proof.status_before_portal === "BLOQUEADO";
  const [mode, setMode] = useState<"view" | "reject">("view");
  const [reason, setReason] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const approve = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("done_date", (proof.portal_submitted_at ?? new Date().toISOString()).slice(0, 10));
      fd.append("channel", "PORTAL");
      fd.append("notes", "Selfie com documento e foto do documento conferidas.");
      if (blocked) fd.append("password", pw);
      const res = await fetch(`/api/backend/provadevida/provas/${proof.id}/register`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Falha ao aprovar.");
      toast.success(body.restabelecidos ? `Aprovada. ${body.restabelecidos} benefício(s) restabelecido(s).` : "Prova de vida aprovada. O segurado foi avisado.");
      onDone();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  const reject = async () => {
    setBusy(true);
    try {
      await api(`provadevida/provas/${proof.id}/reject`, { method: "POST", body: { reason } });
      toast.success("Envio recusado. O segurado foi avisado para enviar de novo.");
      onDone();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  const src = (tipo: string) => `/api/backend/provadevida/provas/${proof.id}/photo?tipo=${tipo}`;
  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Conferir prova de vida enviada pelo Portal</DialogTitle>
          <DialogDescription>{proof.person_name} · {proof.person_cpf}{proof.birth_date ? ` · nasc. ${formatDate(proof.birth_date)}` : ""} · enviada em {proof.portal_submitted_at ? formatDate(proof.portal_submitted_at) : "—"}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3 text-xs">
          <div className="grid gap-3 sm:grid-cols-2">
            {[["selfie", "Selfie segurando o documento"], ["documento", "Foto do documento"]].map(([k, l]) => (
              <div key={k} className="space-y-1">
                <div className="font-medium">{l}</div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <a href={src(k)} target="_blank" rel="noreferrer"><img src={src(k)} alt={l} className="h-64 w-full rounded-lg border bg-muted object-contain" /></a>
              </div>
            ))}
          </div>
          {proof.frames_count > 0 && (
            <div className="space-y-1.5 rounded-lg border bg-muted/40 p-3">
              <div className="font-medium">Gestos feitos na câmera ao vivo (vivacidade)</div>
              <div className="flex flex-wrap gap-2">
                {Array.from({ length: proof.frames_count }).map((_, n) => (
                  <figure key={n} className="w-28 space-y-0.5 text-center">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={`/api/backend/provadevida/provas/${proof.id}/photo?tipo=gesto&n=${n}`} alt={`Gesto ${n + 1}`} className="h-24 w-28 rounded border object-cover" />
                    <figcaption className="text-2xs text-muted-foreground">{proof.portal_liveness.desafios?.[n] ?? `Gesto ${n + 1}`}</figcaption>
                  </figure>
                ))}
              </div>
              <div className="text-2xs text-muted-foreground">Movimento medido: {proof.portal_liveness.movimento ?? "—"} (mínimo 4) · {proof.portal_liveness.metodo}
                {proof.portal_liveness.camera ? ` · câmera: ${proof.portal_liveness.camera}` : ""}. Verificação automática simples — não é biometria; a conferência do rosto é sua.</div>
            </div>
          )}
          <p className="text-muted-foreground">Confira: o rosto da selfie é o mesmo do documento? A pessoa aparece se mexendo nos gestos? O nome e o número do documento estão legíveis e conferem com o cadastro? A foto parece atual?</p>
          {mode === "reject" && <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Explique ao segurado o que precisa ser corrigido (ex.: foto do documento ilegível)" />}
          {mode === "view" && blocked && (
            <label className="block space-y-1"><span className="font-medium">Sua senha (o benefício suspenso será restabelecido)</span>
              <Input type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} /></label>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Fechar</Button>
          {mode === "view" ? <>
            <Button variant="outline" className="text-critical" onClick={() => setMode("reject")} disabled={busy}><XCircle /> Recusar</Button>
            <Button onClick={approve} disabled={busy || (blocked && !pw)}>{busy && <Loader2 className="animate-spin" />}<CheckCircle2 /> Aprovar</Button>
          </> : <Button variant="destructive" onClick={reject} disabled={busy || reason.trim().length < 10}>{busy && <Loader2 className="animate-spin" />} Recusar e avisar o segurado</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}