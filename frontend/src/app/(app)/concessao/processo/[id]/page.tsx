"use client";

import { use, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import {
  Ban, Calculator, Check, CheckCircle2, Download, FileText, Gavel, Loader2, PauseCircle, PlayCircle, Plus, Rocket, Send,
  ShieldCheck, Trash2, Undo2, XCircle,
} from "lucide-react";

import { ChecklistPanel } from "@/components/concessao/checklist-panel";
import { STAGE_VARIANT } from "@/components/concessao/concession-list";
import { useSession } from "@/components/providers/session-provider";
import { FormField } from "@/components/shared/form-field";
import { ErrorState } from "@/components/shared/data-states";
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
import { api, download, fetcher } from "@/lib/api";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  ChecklistResponse, Concession, ConcessionDocumentRow, ConcessionStage, ConcessionStepRow, ParcelRow, RuleComparison,
} from "@/lib/types";

// Mapeamento PREVIBAM: quem atua em cada etapa
const STEPS: [ConcessionStage[], string, string][] = [
  [["INSTRUCAO", "ENQUADRADO", "CALCULADO"], "Instrução", "Benefícios"],
  [["ANALISE_JURIDICA"], "Parecer", "Jurídico"],
  [["CONTROLE_INTERNO"], "Conformidade", "Controle Interno"],
  [["PRESIDENCIA"], "Assinatura", "Presidência"],
  [["ATO_EMITIDO"], "Publicação", "Folha"],
  [["PUBLICADO"], "Implantação", "Folha"],
  [["IMPLANTADO"], "TCE-RJ", "COMPREV"],
];
const MODALITY = [
  [1, "Por idade"], [2, "Por tempo de contribuição"], [3, "Compulsória"], [4, "Por incapacidade permanente"],
  [5, "De professor"], [6, "Especial — atividade de risco"], [7, "Especial — agentes nocivos"],
].map(([value, label]) => ({ value, label: String(label) }));
const VALIDITY = [
  [1, "Data da publicação"], [2, "Data do laudo médico"], [3, "Data do requerimento"], [4, "Data do afastamento"],
  [5, "Data limite de permanência (compulsória)"], [6, "Outra"],
].map(([value, label]) => ({ value, label: String(label) }));
const today = () => new Date().toISOString().slice(0, 10);
// Antes da assinatura da portaria o processo pode ser sobrestado (pausado) ou arquivado por desistência
const PAUSABLE: ConcessionStage[] = ["INSTRUCAO", "ENQUADRADO", "CALCULADO", "ANALISE_JURIDICA", "CONTROLE_INTERNO", "PRESIDENCIA"];

export default function ConcessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequirePermission module="concessao.processos">
      <Detail id={id} />
    </RequirePermission>
  );
}

function Detail({ id }: { id: string }) {
  const { can } = useSession();
  const { data: c, error, mutate } = useSWR<Concession>(`concessoes/${id}`, fetcher);
  const steps = useSWR<ConcessionStepRow[]>(`concessoes/${id}/steps`, fetcher);
  const docs = useSWR<ConcessionDocumentRow[]>(`concessoes/${id}/documents`, fetcher);
  const chk = useSWR<ChecklistResponse>(`concessoes/${id}/checklist`, fetcher);
  if (error) return <ErrorState error={error} />;
  if (!c) return <div className="h-64 animate-pulse rounded-lg bg-muted" />;

  const mod = c.kind === "APOSENTADORIA" ? "concessao.aposentadoria" : c.kind === "PENSAO" ? "concessao.pensao" : "concessao.revisao";
  const reload = () => { mutate(); steps.mutate(); docs.mutate(); chk.mutate(); };
  const run = async (path: string, body?: unknown, ok = "Ato registrado.") => {
    try {
      await api(`concessoes/${id}/${path}`, { method: "POST", body: body ?? {} });
      toast.success(ok);
      reload();
    } catch (err) {
      toast.error((err as Error).message);
      throw err;
    }
  };
  const instr = ["INSTRUCAO", "ENQUADRADO", "CALCULADO"].includes(c.stage);
  const lastReturn = [...(steps.data ?? [])].reverse().find((s) => s.action.startsWith("DEVOLUCAO"));
  const steps2 = c.kind === "REVISAO" ? STEPS.filter(([, l]) => l !== "Conformidade") : STEPS;

  return (
    <>
      <PageHeader
        title={`${c.kind_display} — ${c.person_name || c.person_cpf}`}
        description={<span className="flex flex-wrap items-center gap-2">Processo <Link className="text-primary hover:underline" href={`/protocolo/processos/${c.process}`}>{c.process_code}</Link> · CPF {c.person_cpf}{c.link_label && ` · ${c.link_label}`} <Badge variant={STAGE_VARIANT[c.stage]}>{c.stage_display}</Badge></span>}
        breadcrumb={[{ label: "Concessão de Benefícios", href: "/concessao/processos" }, { label: c.process_code }]}
        actions={c.kind === "APOSENTADORIA" && c.stage !== "INSTRUCAO" && (
          <Link href={`/concessao/processo/${id}/ficha`}><Button variant="outline" size="sm"><FileText /> Ficha FATIMA</Button></Link>
        )}
      />

      {/* Etapas e setores */}
      <Card className="mb-4">
        <ol className="flex flex-wrap gap-1 p-3">
          {steps2.map(([, label, who], i) => {
            const pos = steps2.findIndex(([ss]) => ss.includes((c.stage === "SOBRESTADO" ? c.suspended_from : c.stage) as ConcessionStage));
            const done = i < pos || (label === "TCE-RJ" && !!c.tce_result);
            const cur = i === pos && !done;
            return (
              <li key={label} className={cn("flex items-center gap-1.5 rounded px-2 py-1 text-xs",
                ["INDEFERIDO", "ANULADO", "DESISTENCIA"].includes(c.stage) ? "text-muted-foreground" : done ? "text-success" : cur ? "bg-primary-soft font-semibold text-primary" : "text-muted-foreground")}>
                {done ? <CheckCircle2 className="h-3.5 w-3.5" /> : <span className="flex h-4 w-4 items-center justify-center rounded-full border text-[10px]">{i + 1}</span>}
                {label} <span className="text-2xs font-normal opacity-70">({who})</span>
              </li>
            );
          })}
        </ol>
        {c.stage === "INDEFERIDO" && <div className="border-t px-4 py-2 text-xs text-critical"><b>Indeferido:</b> {c.rejection_reason}</div>}
        {c.stage === "ANULADO" && <div className="border-t px-4 py-2 text-xs text-critical"><b>Anulado:</b> {c.annulment_act}</div>}
        {c.stage === "SOBRESTADO" && (
          <div className="border-t bg-warning-soft px-4 py-2 text-xs text-warning">
            <PauseCircle className="mr-1 inline h-3.5 w-3.5" /><b>Processo sobrestado (pausado)</b> desde {formatDate(c.suspended_since)} na etapa “{c.suspended_from_display}”
            {c.suspended_until && <> — retomada prevista para <b>{formatDate(c.suspended_until)}</b></>}. Motivo: {c.suspension_reason}
          </div>
        )}
        {c.stage === "DESISTENCIA" && (
          <div className="border-t px-4 py-2 text-xs text-muted-foreground">
            <Ban className="mr-1 inline h-3.5 w-3.5" /><b>Arquivado por desistência do requerente</b> em {formatDateTime(c.withdrawn_at)}: {c.withdrawal_reason}. Nenhum benefício foi concedido; o termo de desistência está em Documentos.
          </div>
        )}
        {instr && c.returned_count > 0 && lastReturn && (
          <div className="border-t bg-warning-soft px-4 py-2 text-xs text-warning"><b>Devolvido para correção ({lastReturn.action_display.toLowerCase()}):</b> {lastReturn.text}</div>
        )}
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          {/* ---------------- Instrução (Benefícios) ---------------- */}
          {c.kind === "APOSENTADORIA" && instr && can(mod, "calcular") && <FramePanel c={c} onDone={reload} />}
          {c.kind === "PENSAO" && instr && can(mod, "calcular") && (
            <Card>
              <CardHeader><CardTitle>Pensão — dependentes e cotas</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-xs">
                <p>Óbito do instituidor em <b>{formatDate(c.death_date)}</b>. O cálculo usa os dependentes habilitados à pensão no Cadastro Único na data do óbito.</p>
                <Button size="sm" onClick={() => run("calculate", {}, "Pensão calculada.").catch(() => undefined)}><Calculator /> {c.stage === "CALCULADO" ? "Recalcular" : "Calcular pensão"}</Button>
              </CardContent>
            </Card>
          )}
          {c.kind === "REVISAO" && instr && can(mod, "calcular") && <RevisionPanel c={c} onSubmit={(b) => run("revision", b, "Revisão instruída.")} />}
          {c.kind === "APOSENTADORIA" && c.stage === "ENQUADRADO" && can(mod, "calcular") && (
            <Card><CardContent className="flex items-center justify-between p-4 text-xs">
              <span>Enquadramento concluído. Calcule os proventos.</span>
              <Button size="sm" onClick={() => run("calculate", {}, "Proventos calculados.").catch(() => undefined)}><Calculator /> Calcular proventos</Button>
            </CardContent></Card>
          )}
          {(c.parcels.length > 0 || c.quotas.length > 0) && c.kind !== "REVISAO" && <CalculationCard c={c} canEdit={c.stage === "CALCULADO" && can(mod, "editar")} onSaved={reload} />}
          {c.stage === "CALCULADO" && can(mod, "editar") && (
            <SendCard warnings={c.calculation.avisos ?? []} pending={chk.data?.setor_atual === "BENEFICIOS" ? chk.data.pendentes_setor_atual : []}
              onSend={(ack, pw) => run("send", { acknowledge_warnings: ack, password: pw }, "Checklist assinado. Processo enviado ao Jurídico.")} />
          )}
          {!["DESISTENCIA", "INDEFERIDO"].includes(c.stage) && <ChecklistPanel c={c} data={chk.data} onChanged={reload} />}

          {/* ---------------- Decisões dos setores ---------------- */}
          {c.stage === "ANALISE_JURIDICA" && (can("concessao.juridico", "aprovar")
            ? <OpinionCard title="Parecer jurídico" placeholder="Fundamentação: requisitos constitucionais e legais, regra aplicada, cálculo dos proventos..."
                okLabel="Parecer favorável" noLabel="Devolver para correção" minLen={30}
                okNote="Com o parecer favorável, a minuta de portaria é gerada e entregue ao setor de Benefícios."
                onDecide={(ok, text, pw) => run("legal", { favorable: ok, text, password: pw }, ok ? "Parecer favorável registrado. Minuta de portaria gerada." : "Processo devolvido ao setor de Benefícios.")} />
            : <Waiting who="Procuradoria Jurídica" what="parecer jurídico" />)}
          {c.stage === "CONTROLE_INTERNO" && (can("concessao.controle_interno", "aprovar")
            ? <OpinionCard title="Análise de conformidade (Controle Interno)" placeholder="Exatidão das informações, regras aplicadas e memória de cálculo..."
                okLabel="Conforme" noLabel="Não conforme — devolver" minLen={20}
                onDecide={(ok, text, pw) => run("compliance", { conform: ok, text, password: pw }, ok ? "Conformidade registrada. Encaminhado à Presidência." : "Processo devolvido ao setor de Benefícios.")} />
            : <Waiting who="Controle Interno" what="análise de conformidade" />)}
          {c.stage === "PRESIDENCIA" && (can("concessao.presidencia", "aprovar")
            ? <SignCard c={c} onSign={(b) => run("sign", b, "Portaria assinada. Documento gerado e entregue ao setor de Benefícios.")}
                onReject={(b) => run("reject", b, "Requerimento indeferido. Ofício de ciência gerado.")} />
            : <Waiting who="Presidência" what="assinatura da portaria" />)}
          {c.stage === "ATO_EMITIDO" && (can("concessao.implantacao", "aprovar")
            ? <PublishCard pending={chk.data?.setor_atual === "FOLHA" ? chk.data.pendentes_setor_atual : []} onPublish={(b) => run("publish", b, "Publicação registrada. Checklist da Folha assinado.")} />
            : <Waiting who="setor de Folha de Pagamento" what="publicação da portaria" />)}
          {c.stage === "PUBLICADO" && (can("concessao.implantacao", "aprovar")
            ? <ImplantCard c={c} onImplant={(pw) => run("implant", { password: pw }, c.kind === "REVISAO" ? "Revisão aplicada na folha." : "Benefício implantado na folha.")} />
            : <Waiting who="setor de Folha de Pagamento" what="implantação em folha" />)}
          {(PAUSABLE.includes(c.stage) || c.stage === "SOBRESTADO") && can(mod, "editar") && <PauseCard c={c} run={run} />}
          {c.stage === "IMPLANTADO" && (
            <>
              <Card className="border-success-border"><CardContent className="p-4 text-xs text-success">
                <CheckCircle2 className="mr-1 inline h-4 w-4" /> {c.kind === "REVISAO" ? "Revisão aplicada" : "Implantado"} em {formatDateTime(c.implanted_at)}. Veja em <Link href="/folha/beneficiarios" className="underline">Folha › Beneficiários</Link>.
              </CardContent></Card>
              <TceCard c={c} canEdit={can("concessao.tce", "editar")} canAnnul={can("concessao.presidencia", "aprovar")} run={run} />
            </>
          )}
        </div>

        <div className="space-y-4">
          <Documents id={id} docs={docs.data} />
          <Summary c={c} />
          <Trail steps={steps.data} />
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ peças de decisão
function ActionCard({ icon: Icon, title, text, action, tone }: { icon: typeof Send; title: string; text: React.ReactNode; action?: React.ReactNode; tone?: "primary" }) {
  return (
    <Card className={tone === "primary" ? "border-primary/40" : undefined}>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-xs">
        <div className="max-w-xl"><div className="mb-0.5 flex items-center gap-1.5 font-semibold"><Icon className="h-4 w-4 text-primary" /> {title}</div>{text}</div>
        {action}
      </CardContent>
    </Card>
  );
}

/** Envio ao Jurídico: checklist completo, ciência dos avisos e senha (assina o checklist de Benefícios). */
function SendCard({ warnings, pending, onSend }: { warnings: string[]; pending: string[]; onSend: (ack: boolean, pw: string) => Promise<void> }) {
  const [ack, setAck] = useState(false);
  const [signing, setSigning] = useState(false);
  return (
    <ActionCard icon={Send} title="Enviar ao Jurídico" tone="primary"
      text={<>
        Concluída a instrução (tempo, enquadramento e cálculo), o processo segue para parecer da Procuradoria Jurídica. Depois disso a instrução fica bloqueada, salvo devolução.
        {pending.length > 0 && (
          <div className="mt-2 rounded border border-critical/40 bg-critical/5 px-3 py-2 text-critical">
            <b>Faltam documentos no checklist:</b> {pending.join("; ")}.
          </div>
        )}
        {warnings.length > 0 && (
          <div className="mt-2 space-y-1 rounded border border-warning/40 bg-warning-soft px-3 py-2">
            <div className="font-semibold text-warning">Avisos do cálculo — confira antes de enviar:</div>
            <ul className="list-disc space-y-0.5 pl-4">{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            <label className="flex items-center gap-2 font-medium"><Checkbox checked={ack} onChange={(e) => setAck(e.target.checked)} /> Conferi os avisos (a ciência fica registrada na trilha)</label>
          </div>
        )}
      </>}
      action={<>
        <Button size="sm" disabled={pending.length > 0 || (warnings.length > 0 && !ack)} onClick={() => setSigning(true)}><Send /> Assinar e enviar ao Jurídico</Button>
        {signing && <SignatureDialog title="Assinar checklist e enviar ao Jurídico" confirmLabel="Assinar e enviar"
          summary={<>O sistema gera o relatório de instrução, calcula o código SHA-256 dos documentos de Benefícios e registra no processo digital.</>}
          onClose={() => setSigning(false)} onConfirm={(pw) => onSend(ack, pw)} />}
      </>} />
  );
}

/** Sobrestar (pausar), retomar ou arquivar por desistência — sempre com motivo e senha; tudo vai para a trilha. */
function PauseCard({ c, run }: { c: Concession; run: (p: string, b?: unknown, ok?: string) => Promise<void> }) {
  const [mode, setMode] = useState<"suspend" | "resume" | "withdraw" | null>(null);
  const [f, setF] = useState({ reason: "", until: "", attached: false });
  const [signing, setSigning] = useState(false);
  const paused = c.stage === "SOBRESTADO";
  const min = mode === "resume" ? 10 : 20;
  const valid = f.reason.trim().length >= min && (mode !== "withdraw" || f.attached);
  const close = () => { setMode(null); setSigning(false); setF({ reason: "", until: "", attached: false }); };
  const title = mode === "suspend" ? "Sobrestar (pausar) o processo" : mode === "resume" ? "Retomar o processo" : "Desistência do requerente";
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-xs">
        <div className="max-w-xl text-muted-foreground">
          {paused
            ? "O processo está pausado. Retome quando o servidor confirmar o pedido ou registre a desistência."
            : "Se o servidor pedir prazo, o processo pode ser pausado; se desistir de se aposentar, registre a desistência (arquiva sem conceder)."}
        </div>
        <div className="flex flex-wrap gap-2">
          {paused
            ? <Button size="sm" onClick={() => setMode("resume")}><PlayCircle /> Retomar</Button>
            : <Button size="sm" variant="outline" onClick={() => setMode("suspend")}><PauseCircle /> Sobrestar (pausar)</Button>}
          <Button size="sm" variant="outline" className="text-critical" onClick={() => setMode("withdraw")}><Ban /> Desistência</Button>
        </div>
      </CardContent>
      {mode && !signing && (
        <Dialog open onOpenChange={(v) => !v && close()}>
          <DialogContent size="sm">
            <DialogHeader>
              <DialogTitle>{title}</DialogTitle>
              <DialogDescription>
                {mode === "suspend" && "O processo fica parado na etapa atual; os dias de pausa não contam no prazo do Protocolo."}
                {mode === "resume" && `O processo volta para a etapa “${c.suspended_from_display}”.`}
                {mode === "withdraw" && "O processo é arquivado sem conceder o benefício e o termo de desistência é gerado. O servidor pode fazer novo pedido depois."}
              </DialogDescription>
            </DialogHeader>
            <DialogBody className="space-y-3">
              <FormField label={mode === "resume" ? "Motivo da retomada" : mode === "suspend" ? "Motivo do sobrestamento" : "Motivo da desistência (informado pelo servidor)"} htmlFor="pz-r" hint={`Mínimo de ${min} caracteres.`} required>
                <Textarea id="pz-r" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} />
              </FormField>
              {mode === "suspend" && (
                <FormField label="Previsão de retomada (opcional)" htmlFor="pz-u" hint="Na data, a Central de Alertas avisa o setor.">
                  <Input id="pz-u" type="date" value={f.until} onChange={(e) => setF({ ...f, until: e.target.value })} />
                </FormField>
              )}
              {mode === "withdraw" && (
                <label className="flex items-start gap-2"><Checkbox checked={f.attached} onChange={(e) => setF({ ...f, attached: e.target.checked })} /> O pedido de desistência assinado pelo servidor está juntado ao processo</label>
              )}
            </DialogBody>
            <DialogFooter>
              <Button variant="outline" onClick={close}>Cancelar</Button>
              <Button variant={mode === "withdraw" ? "destructive" : "default"} disabled={!valid} onClick={() => setSigning(true)}>Continuar</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {mode && signing && (
        <SignatureDialog title={title} destructive={mode === "withdraw"} confirmLabel="Confirmar"
          summary={<p className="whitespace-pre-line">{f.reason}</p>} onClose={close}
          onConfirm={(pw) => mode === "suspend"
            ? run("suspend", { reason: f.reason, until: f.until || null, password: pw }, "Processo sobrestado (pausado).")
            : mode === "resume"
              ? run("resume", { text: f.reason, password: pw }, "Processo retomado.")
              : run("withdraw", { reason: f.reason, request_attached: f.attached, password: pw }, "Processo arquivado por desistência. Termo gerado.")} />
      )}
    </Card>
  );
}

function Waiting({ who, what }: { who: string; what: string }) {
  return <ActionCard icon={Loader2} title={`Aguardando ${what}`} text={<>Esta etapa é praticada pelo(a) <b>{who}</b>. Seu perfil pode acompanhar, mas não decidir.</>} />;
}

/** Pede a senha do usuário (assinatura eletrônica) antes de concluir um ato decisivo. */
function SignatureDialog({ title, summary, confirmLabel, destructive, onConfirm, onClose }: {
  title: string; summary: React.ReactNode; confirmLabel: string; destructive?: boolean;
  onConfirm: (password: string) => Promise<void>; onClose: () => void;
}) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" /> {title}</DialogTitle>
          <DialogDescription asChild><div>{summary}</div></DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-2">
          <FormField label="Sua senha (assinatura eletrônica)" htmlFor="sig-pw" hint="O ato fica registrado na trilha do processo com seu nome, data, hora e um código de verificação.">
            <Input id="sig-pw" type="password" autoComplete="current-password" autoFocus value={pw} onChange={(e) => setPw(e.target.value)} />
          </FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button variant={destructive ? "destructive" : "default"} disabled={!pw || busy}
            onClick={async () => { setBusy(true); try { await onConfirm(pw); onClose(); } catch { /* mensagem já exibida */ } finally { setBusy(false); } }}>
            {busy && <Loader2 className="animate-spin" />} {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OpinionCard({ title, placeholder, okLabel, noLabel, minLen, okNote, onDecide }: {
  title: string; placeholder: string; okLabel: string; noLabel: string; minLen: number; okNote?: string;
  onDecide: (ok: boolean, text: string, password: string) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [decision, setDecision] = useState<boolean | null>(null);
  const valid = text.trim().length >= minLen;
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-1.5"><Gavel className="h-4 w-4 text-primary" /> {title}</CardTitle></CardHeader>
      <CardContent className="space-y-2 text-xs">
        <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} className="min-h-[110px]" />
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={!valid} onClick={() => setDecision(true)}><Check /> {okLabel}</Button>
          <Button variant="outline" disabled={!valid} onClick={() => setDecision(false)}><Undo2 /> {noLabel}</Button>
          {!valid && <span className="text-muted-foreground">Mínimo de {minLen} caracteres.</span>}
        </div>
        {okNote && <p className="text-muted-foreground">{okNote}</p>}
      </CardContent>
      {decision !== null && (
        <SignatureDialog title={decision ? okLabel : noLabel} confirmLabel="Assinar e registrar" destructive={!decision}
          summary={<p className="whitespace-pre-line">{text}</p>} onClose={() => setDecision(null)}
          onConfirm={(pw) => onDecide(decision, text, pw)} />
      )}
    </Card>
  );
}

function SignCard({ c, onSign, onReject }: { c: Concession; onSign: (b: Record<string, unknown>) => Promise<void>; onReject: (b: Record<string, unknown>) => Promise<void> }) {
  const [f, setF] = useState({ nature: "PORTARIA", number: "", act_date: today() });
  const [mode, setMode] = useState<"sign" | "reject" | "reject-sign" | null>(null);
  const [reason, setReason] = useState("");
  return (
    <Card className="border-primary/40">
      <CardHeader><CardTitle className="flex items-center gap-1.5"><Gavel className="h-4 w-4 text-primary" /> Assinatura da portaria (Presidência)</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-xs">
        <p>Confira a <b>minuta</b> (em Documentos), os pareceres e o cálculo. Ao assinar, os valores ficam <b>fixados</b>: qualquer alteração posterior bloqueia a implantação.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField label="Natureza" htmlFor="sg-n"><Select id="sg-n" value={f.nature} onChange={(e) => setF({ ...f, nature: e.target.value })}>
            <option value="PORTARIA">Portaria</option><option value="DECRETO">Decreto</option><option value="RESOLUCAO">Resolução</option><option value="OUTROS">Outros</option></Select></FormField>
          <FormField label="Número" htmlFor="sg-num" required><Input id="sg-num" value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} placeholder="ex.: 123/2026" /></FormField>
          <FormField label="Data" htmlFor="sg-d" required><Input id="sg-d" type="date" value={f.act_date} onChange={(e) => setF({ ...f, act_date: e.target.value })} /></FormField>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!f.number.trim()} onClick={() => setMode("sign")}><Gavel /> Assinar portaria</Button>
          <Button variant="outline" onClick={() => setMode("reject")}><XCircle /> Indeferir</Button>
        </div>
      </CardContent>
      {mode === "sign" && (
        <SignatureDialog title="Assinar portaria" confirmLabel="Assinar"
          summary={<>{f.nature === "PORTARIA" ? "Portaria" : f.nature} nº <b>{f.number}</b> de {formatDate(f.act_date)} — {c.kind_display.toLowerCase()} de <b>{c.person_name}</b>, valor <b>{c.total ? formatCurrency(c.total) : "—"}</b>{c.validity_date ? `, a partir de ${formatDate(c.validity_date)}` : ""}.</>}
          onClose={() => setMode(null)} onConfirm={(pw) => onSign({ ...f, password: pw })} />
      )}
      {mode === "reject" && (
        <Dialog open onOpenChange={(v) => !v && setMode(null)}>
          <DialogContent size="sm">
            <DialogHeader><DialogTitle>Indeferir o requerimento</DialogTitle>
              <DialogDescription>Fundamente (mínimo de 30 caracteres). O sistema gera o ofício de ciência para o setor de Benefícios.</DialogDescription></DialogHeader>
            <DialogBody><Textarea value={reason} onChange={(e) => setReason(e.target.value)} className="min-h-[100px]" /></DialogBody>
            <DialogFooter>
              <Button variant="outline" onClick={() => setMode(null)}>Cancelar</Button>
              <Button variant="destructive" disabled={reason.trim().length < 30} onClick={() => setMode("reject-sign")}>Continuar</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {mode === "reject-sign" && (
        <SignatureDialog title="Indeferir requerimento" confirmLabel="Assinar indeferimento" destructive
          summary={<p className="whitespace-pre-line">{reason}</p>} onClose={() => setMode(null)}
          onConfirm={(pw) => onReject({ reason, password: pw })} />
      )}
    </Card>
  );
}

function PublishCard({ pending, onPublish }: { pending: string[]; onPublish: (b: Record<string, unknown>) => Promise<void> }) {
  const [f, setF] = useState({ publication_date: today(), media: "" });
  const [signing, setSigning] = useState(false);
  return (
    <Card>
      <CardHeader><CardTitle>Publicação da portaria</CardTitle></CardHeader>
      <CardContent className="grid gap-3 text-xs sm:grid-cols-3">
        <FormField label="Data de publicação" htmlFor="pb-d"><Input id="pb-d" type="date" value={f.publication_date} onChange={(e) => setF({ ...f, publication_date: e.target.value })} /></FormField>
        <FormField label="Meio (ex.: Notícia Oficial nº e data)" htmlFor="pb-m" className="sm:col-span-2"><Input id="pb-m" value={f.media} onChange={(e) => setF({ ...f, media: e.target.value })} /></FormField>
        {pending.length > 0 && <div className="rounded border border-critical/40 bg-critical/5 px-3 py-2 text-critical sm:col-span-3"><b>Anexe no checklist:</b> {pending.join("; ")}.</div>}
        <div className="sm:col-span-3"><Button disabled={pending.length > 0 || f.media.trim().length < 5} onClick={() => setSigning(true)}>Registrar publicação</Button></div>
        {signing && <SignatureDialog title="Registrar publicação" confirmLabel="Assinar e registrar"
          summary={<>Publicação em {formatDate(f.publication_date)} — {f.media}. O checklist da Folha é assinado com código SHA-256.</>}
          onClose={() => setSigning(false)} onConfirm={(pw) => onPublish({ ...f, password: pw })} />}
      </CardContent>
    </Card>
  );
}

function ImplantCard({ c, onImplant }: { c: Concession; onImplant: (pw: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const what = c.kind === "REVISAO" ? `alterar o valor de ${c.revised_benefit_label} para ${c.total ? formatCurrency(c.total) : "—"}`
    : c.kind === "PENSAO" ? `incluir ${c.quotas.length} cota(s) de pensão, total ${c.total ? formatCurrency(c.total) : "—"}`
      : `incluir a aposentadoria de ${c.person_name}, ${c.total ? formatCurrency(c.total) : "—"}, e encerrar o vínculo como aposentado`;
  return (
    <ActionCard icon={Rocket} title="Implantação em folha" tone="primary"
      text={<>Portaria {c.act_number} publicada em {formatDate(c.publication_date)}. A implantação vai <b>{what}</b>, a partir de {formatDate(c.validity_date)}. O sistema confere se os valores são exatamente os assinados.</>}
      action={<>
        <Button onClick={() => setOpen(true)}><Rocket /> {c.kind === "REVISAO" ? "Aplicar revisão" : "Implantar na folha"}</Button>
        {open && <SignatureDialog title={c.kind === "REVISAO" ? "Aplicar revisão na folha" : "Implantar na folha"} confirmLabel="Confirmar implantação"
          summary={<>Vai {what}. Esta operação é registrada e auditável.</>} onClose={() => setOpen(false)} onConfirm={onImplant} />}
      </>} />
  );
}

function TceCard({ c, canEdit, canAnnul, run }: { c: Concession; canEdit: boolean; canAnnul: boolean; run: (p: string, b?: unknown, ok?: string) => Promise<void> }) {
  const [send, setSend] = useState({ sent_date: today(), reference: "" });
  const [judg, setJudg] = useState({ result: "LEGAL", result_date: today(), notes: "" });
  const [annul, setAnnul] = useState({ number: "", act_date: today() });
  const [signing, setSigning] = useState(false);
  return (
    <Card>
      <CardHeader><CardTitle>Registro no TCE-RJ</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-xs">
        {c.tce_sent_date
          ? <p>Enviado ao TCE-RJ em <b>{formatDate(c.tce_sent_date)}</b> — processo {c.tce_reference}.{c.tce_result && <> Julgamento: <b>{c.tce_result_display}</b> em {formatDate(c.tce_result_date)}. {c.tce_notes}</>}</p>
          : <p className="text-muted-foreground">Após a implantação, o setor de COMPREV envia os dados ao TCE-RJ (Deliberação 260 — Ficha FATIMA e SalContr.txt).</p>}
        {canEdit && !c.tce_sent_date && (
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField label="Data do envio" htmlFor="tc-d"><Input id="tc-d" type="date" value={send.sent_date} onChange={(e) => setSend({ ...send, sent_date: e.target.value })} /></FormField>
            <FormField label="Nº do processo no TCE-RJ" htmlFor="tc-r" className="sm:col-span-2"><Input id="tc-r" value={send.reference} onChange={(e) => setSend({ ...send, reference: e.target.value })} /></FormField>
            <div><Button size="sm" disabled={!send.reference.trim()} onClick={() => run("tce-send", send, "Envio ao TCE-RJ registrado.").catch(() => undefined)}>Registrar envio</Button></div>
          </div>
        )}
        {canEdit && c.tce_sent_date && !c.tce_result && (
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField label="Julgamento" htmlFor="tj-r"><Select id="tj-r" value={judg.result} onChange={(e) => setJudg({ ...judg, result: e.target.value })}>
              <option value="LEGAL">Legal (registrado)</option><option value="RESSALVA">Legal com ressalva</option><option value="ILEGAL">Ilegal (negado registro)</option></Select></FormField>
            <FormField label="Data" htmlFor="tj-d"><Input id="tj-d" type="date" value={judg.result_date} onChange={(e) => setJudg({ ...judg, result_date: e.target.value })} /></FormField>
            <FormField label="Observações" htmlFor="tj-n"><Input id="tj-n" value={judg.notes} onChange={(e) => setJudg({ ...judg, notes: e.target.value })} /></FormField>
            <div><Button size="sm" onClick={() => run("tce-judgment", judg, judg.result === "ILEGAL" ? "Julgamento registrado. Minuta de portaria de anulação gerada." : "Julgamento registrado.").catch(() => undefined)}>Registrar julgamento</Button></div>
          </div>
        )}
        {c.tce_result === "ILEGAL" && canAnnul && (
          <div className="rounded border border-critical/40 bg-critical/5 p-3">
            <p className="mb-2"><b>Anulação.</b> O TCE-RJ julgou ilegal. A anulação exclui o benefício da folha{c.kind === "APOSENTADORIA" ? " e devolve o servidor à condição de ativo (comunicar o RH para reimplantação na folha dos ativos)" : ""}.</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <FormField label="Nº da portaria de anulação" htmlFor="an-n"><Input id="an-n" value={annul.number} onChange={(e) => setAnnul({ ...annul, number: e.target.value })} /></FormField>
              <FormField label="Data" htmlFor="an-d"><Input id="an-d" type="date" value={annul.act_date} onChange={(e) => setAnnul({ ...annul, act_date: e.target.value })} /></FormField>
              <div className="self-end"><Button variant="destructive" size="sm" disabled={!annul.number.trim()} onClick={() => setSigning(true)}>Anular concessão</Button></div>
            </div>
          </div>
        )}
      </CardContent>
      {signing && <SignatureDialog title="Anular concessão" destructive confirmLabel="Assinar anulação"
        summary={<>Portaria de anulação nº <b>{annul.number}</b> de {formatDate(annul.act_date)}.</>} onClose={() => setSigning(false)}
        onConfirm={(pw) => run("annul", { ...annul, password: pw }, "Concessão anulada. Portaria de anulação gerada.")} />}
    </Card>
  );
}

function RevisionPanel({ c, onSubmit }: { c: Concession; onSubmit: (b: Record<string, unknown>) => Promise<void> }) {
  const [f, setF] = useState({ amount: c.total ? c.total.replace(".", ",") : "", validity_date: c.validity_date ?? today(), reason: c.revision_reason });
  const [busy, setBusy] = useState(false);
  return (
    <Card>
      <CardHeader><CardTitle>Instrução da revisão</CardTitle></CardHeader>
      <CardContent className="grid gap-3 text-xs sm:grid-cols-2">
        <div className="sm:col-span-2 rounded border bg-muted/40 px-3 py-2">Benefício revisto: <b>{c.revised_benefit_label}</b></div>
        <FormField label="Novo valor mensal (R$)" htmlFor="rv-a" required><Input id="rv-a" inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} placeholder="0,00" /></FormField>
        <FormField label="A partir de" htmlFor="rv-d" required><Input id="rv-d" type="date" value={f.validity_date} onChange={(e) => setF({ ...f, validity_date: e.target.value })} /></FormField>
        <FormField label="Motivo / fundamento da revisão" htmlFor="rv-r" required className="sm:col-span-2"><Textarea id="rv-r" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></FormField>
        <div className="sm:col-span-2"><Button disabled={busy} onClick={async () => { setBusy(true); try { await onSubmit(f); } catch { /* exibida */ } finally { setBusy(false); } }}>
          {busy && <Loader2 className="animate-spin" />} Salvar instrução</Button>
          <span className="ml-3 text-2xs text-muted-foreground">O novo valor só vale depois do parecer jurídico, da portaria assinada e da publicação.</span></div>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ documentos, resumo e trilha
function Documents({ id, docs }: { id: string; docs?: ConcessionDocumentRow[] }) {
  return (
    <Card>
      <CardHeader><CardTitle>Documentos gerados</CardTitle></CardHeader>
      <CardContent className="space-y-1.5 text-xs">
        {!docs?.length && <p className="text-muted-foreground">A minuta de portaria é gerada automaticamente após o parecer jurídico favorável; a portaria, na assinatura. Ambas ficam também anexadas ao processo do Protocolo.</p>}
        {docs?.map((d) => (
          <div key={d.id} className="flex items-center justify-between gap-2 rounded border px-2 py-1.5">
            <div className="min-w-0"><div className="font-medium">{d.kind_display} <span className="text-muted-foreground">v{d.version}</span></div>
              <div className="truncate text-2xs text-muted-foreground" title={d.sha256}>{formatDateTime(d.created_at)} · SHA-256 {d.sha256.slice(0, 12)}…</div></div>
            <Button size="icon" variant="ghost" className="h-7 w-7 shrink-0" aria-label="Baixar"
              onClick={() => download(`concessoes/${id}/documents/${d.id}/download`, d.file_name).catch((e) => toast.error((e as Error).message))}><Download /></Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function Trail({ steps }: { steps?: ConcessionStepRow[] }) {
  return (
    <Card>
      <CardHeader><CardTitle>Trilha do processo</CardTitle></CardHeader>
      <CardContent className="text-xs">
        <ol className="space-y-2 border-l pl-3">
          {steps?.map((s) => (
            <li key={s.id}>
              <div className="flex flex-wrap items-center gap-1"><b>{s.action_display}</b>{s.signed && <Badge variant="success" className="gap-1"><ShieldCheck className="h-3 w-3" /> assinado</Badge>}</div>
              <div className="text-2xs text-muted-foreground">{s.user_name} · {formatDateTime(s.created_at)}{s.signature_hash && <> · código {s.signature_hash.slice(0, 10)}</>}</div>
              {s.text && <div className="whitespace-pre-line">{s.text}</div>}
              {s.data.documento ? <div className="text-2xs">{String(s.data.documento)}</div> : null}
              {(s.data.checklist as { hash_checklist?: string } | undefined)?.hash_checklist ? (
                <div className="text-2xs text-success">Checklist assinado · código <span className="font-mono" title={(s.data.checklist as { hash_checklist: string }).hash_checklist}>{(s.data.checklist as { hash_checklist: string }).hash_checklist.slice(0, 16)}…</span></div>
              ) : null}
            </li>
          ))}
          {steps?.length === 0 && <li className="text-muted-foreground">Nenhum ato registrado.</li>}
        </ol>
      </CardContent>
    </Card>
  );
}

function Summary({ c }: { c: Concession }) {
  const r = c.analysis.regra;
  const Row = ({ k, v }: { k: string; v: React.ReactNode }) => v ? <div className="grid grid-cols-5 gap-2"><span className="col-span-2 text-muted-foreground">{k}</span><span className="col-span-3">{v}</span></div> : null;
  return (
    <Card className="self-start">
      <CardHeader><CardTitle>Resumo</CardTitle></CardHeader>
      <CardContent className="space-y-1.5 text-xs">
        <Row k="Benefício revisto" v={c.revised_benefit_label} />
        <Row k="Modalidade" v={c.modality_display} />
        <Row k="Fundamentação" v={c.legal_basis} />
        <Row k="Legislação local" v={c.local_legal_basis} />
        <Row k="Data de validade" v={c.validity_date && `${formatDate(c.validity_date)}${c.validity_class_display ? ` (${c.validity_class_display})` : ""}`} />
        <Row k="Óbito" v={c.death_date && formatDate(c.death_date)} />
        <Row k="Valor" v={c.total && <b>{formatCurrency(c.total)}</b>} />
        <Row k="Integralidade / paridade" v={c.stage !== "INSTRUCAO" && c.kind !== "REVISAO" ? `${c.integralidade ? "Sim" : "Não"} / ${c.paridade ? "Sim" : "Não"}` : ""} />
        <Row k="Parecer jurídico" v={c.opinion && <span className="whitespace-pre-line">{c.opinion}</span>} />
        <Row k="Controle Interno" v={c.compliance_opinion && <span className="whitespace-pre-line">{c.compliance_opinion}</span>} />
        <Row k="Portaria" v={c.act_number && <>{c.act_nature_display} nº {c.act_number} de {formatDate(c.act_date)}<br /><span className="text-muted-foreground">assinada por {c.approved_by_name}</span></>} />
        <Row k="Publicação" v={c.publication_date && `${formatDate(c.publication_date)} — ${c.publication_media}`} />
        <Row k="Valores fixados" v={c.signed_hash && <span className="font-mono text-2xs">{c.signed_hash.slice(0, 16)}…</span>} />
        {r && (
          <div className="mt-2 border-t pt-2">
            <div className="section-label mb-1">Enquadramento</div>
            <div className="font-medium">{r.nome}</div>
            <div className="text-2xs text-muted-foreground">{r.fundamento} · requisitos cumpridos em {formatDate(r.data_cumprimento)}</div>
            {r.data_referencia && <div className="text-2xs text-muted-foreground">Requisitos apurados em {formatDate(r.data_referencia)}:</div>}
            <ul className="mt-1 space-y-0.5 text-2xs">{r.requisitos.map((q) => <li key={q.descricao}><Check className="mr-1 inline h-3 w-3 text-success" />{q.descricao}: {q.atual} (exigido {q.exigido})</li>)}</ul>
            {c.analysis.data_base_calculo && <div className="mt-1 text-2xs">Data-base da média e do tempo: <b>{formatDate(c.analysis.data_base_calculo)}</b> — {c.analysis.data_base_motivo}</div>}
            {c.analysis.opcao && (
              <div className="mt-1 rounded border border-warning/40 bg-warning-soft px-2 py-1 text-2xs">
                <b>Opção por regra menos vantajosa</b> (mais favorável: {c.analysis.opcao.melhor_regra}, {formatCurrency(c.analysis.opcao.melhor_valor)}). {c.analysis.opcao.justificativa} — termo de opção juntado.
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FramePanel({ c, onDone }: { c: Concession; onDone: () => void }) {
  const [validity, setValidity] = useState(c.validity_date ?? new Date().toISOString().slice(0, 10));
  const [base, setBase] = useState({ date: "", reason: "" });
  const cmpUrl = `concessoes/${c.id}/comparativo?validity_date=${validity}${base.date ? `&base_date=${base.date}` : ""}`;
  const cmp = useSWR<RuleComparison>(validity ? cmpUrl : null, fetcher);
  const [f, setF] = useState({
    rule: c.rule_code || "", modality: c.modality ? String(c.modality) : "", validity_class: c.validity_class ? String(c.validity_class) : "1",
    validity_legal_basis: c.validity_legal_basis, invalidity_cause: c.invalidity_cause ? String(c.invalidity_cause) : "", cid: c.cid,
    medical_report_date: c.medical_report_date ?? "", judicial: c.judicial, judicial_process: c.judicial_process,
  });
  const [option, setOption] = useState({ reason: "", signed: false });
  const [busy, setBusy] = useState(false);
  const invalidity = f.modality === "4";
  const rows = cmp.data?.regras ?? [];
  const best = rows.find((r) => r.codigo === cmp.data?.melhor);
  const chosen = rows.find((r) => r.codigo === f.rule);
  const lessFavorable = !!(best && chosen && best.codigo !== chosen.codigo && Number(best.valor) > Number(chosen.valor ?? 0));

  const submit = async () => {
    setBusy(true);
    try {
      await api(`concessoes/${c.id}/frame`, { method: "POST", body: {
        ...f, rule: invalidity ? null : f.rule, validity_date: validity, modality: f.modality || null,
        invalidity_cause: f.invalidity_cause || null, medical_report_date: f.medical_report_date || null,
        base_date: base.date || null, base_date_reason: base.reason,
        option_reason: lessFavorable ? option.reason : "", option_signed: lessFavorable && option.signed } });
      toast.success("Enquadramento registrado.");
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  return (
    <Card>
      <CardHeader><CardTitle>Enquadramento</CardTitle></CardHeader>
      <CardContent className="grid gap-3 text-xs sm:grid-cols-2">
        <FormField label="Data de validade (início da aposentadoria)" htmlFor="fr-val" required>
          <Input id="fr-val" type="date" value={validity} onChange={(e) => setValidity(e.target.value)} />
        </FormField>
        <FormField label="Classificação da data de validade" htmlFor="fr-cls" required>
          <Select id="fr-cls" value={f.validity_class} onChange={set("validity_class")}>{VALIDITY.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
        </FormField>
        <FormField label="Modalidade" htmlFor="fr-mod" hint="Vazio = definida pela regra.">
          <Select id="fr-mod" value={f.modality} onChange={set("modality")}><option value="">Pela regra</option>{MODALITY.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
        </FormField>
        <FormField label="Data-base da média e do tempo" htmlFor="fr-base"
          hint={`Padrão: abertura do processo${cmp.data && !base.date ? ` (${formatDate(cmp.data.data_base)})` : ""}. Altere só com justificativa.`}>
          <Input id="fr-base" type="date" value={base.date} onChange={(e) => setBase((b) => ({ ...b, date: e.target.value }))} />
        </FormField>
        {base.date && (
          <FormField label="Justificativa da data-base diferente" htmlFor="fr-base-r" required>
            <Input id="fr-base-r" value={base.reason} onChange={(e) => setBase((b) => ({ ...b, reason: e.target.value }))} placeholder="mínimo de 20 caracteres" />
          </FormField>
        )}
        {!invalidity && (
          <div className="sm:col-span-2 space-y-2">
            <div className="section-label">Regras cumpridas até a data de validade — escolha a regra</div>
            {cmp.isLoading && <div className="text-muted-foreground"><Loader2 className="mr-1 inline h-3 w-3 animate-spin" /> Comparando regras...</div>}
            {cmp.data && rows.length === 0 && <div className="text-muted-foreground">Nenhuma regra cumprida nesta data.</div>}
            {rows.length > 0 && (
              <Table>
                <TableHeader><TableRow><TableHead /><TableHead>Regra</TableHead><TableHead>Cumprida em</TableHead><TableHead>Forma de cálculo</TableHead><TableHead className="text-right">Valor estimado</TableHead></TableRow></TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.codigo} className={cn("cursor-pointer", f.rule === r.codigo && "bg-primary-soft")} onClick={() => setF((s) => ({ ...s, rule: r.codigo }))}>
                      <TableCell><input type="radio" name="fr-rule" aria-label={r.nome} checked={f.rule === r.codigo} onChange={() => setF((s) => ({ ...s, rule: r.codigo }))} /></TableCell>
                      <TableCell><div className="font-medium">{r.nome} {r.codigo === cmp.data?.melhor && <Badge variant="success">mais favorável</Badge>}</div><div className="text-2xs text-muted-foreground">{r.fundamento} · {r.paridade}</div></TableCell>
                      <TableCell>{formatDate(r.data_cumprimento)}</TableCell>
                      <TableCell className="text-2xs">{r.forma}{r.avisos.map((a) => <div key={a} className="text-warning">{a}</div>)}</TableCell>
                      <TableCell className="text-right tabular">{r.valor ? formatCurrency(r.valor) : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {cmp.data && (cmp.data.pendencias.length > 0 || cmp.data.avisos.length > 0) && (
              <div className="rounded border border-warning/40 bg-warning-soft px-3 py-2 text-2xs">
                {cmp.data.pendencias.map((p) => <div key={p} className="text-critical"><b>Impede o cálculo:</b> {p}</div>)}
                {cmp.data.avisos.map((a) => <div key={a} className="text-warning">{a}</div>)}
                <div className="text-muted-foreground">{cmp.data.observacao}</div>
              </div>
            )}
            {lessFavorable && best && (
              <div className="space-y-2 rounded border border-critical/40 bg-critical/5 p-3">
                <p><b>Regra menos vantajosa.</b> A regra “{best.nome}” resulta em {formatCurrency(best.valor!)}. O servidor tem direito ao benefício mais favorável (Emenda à LOM 28/2025, art. 5º, § 2º). Para seguir com esta regra, registre a justificativa e confirme o termo de opção do servidor.</p>
                <Textarea value={option.reason} onChange={(e) => setOption((o) => ({ ...o, reason: e.target.value }))} placeholder="Justificativa (mínimo de 30 caracteres)" />
                <label className="flex items-center gap-2"><Checkbox checked={option.signed} onChange={(e) => setOption((o) => ({ ...o, signed: e.target.checked }))} /> O termo de opção assinado pelo servidor está juntado ao processo</label>
              </div>
            )}
          </div>
        )}
        {invalidity && (
          <>
            <FormField label="Causa da incapacidade" htmlFor="fr-cause" required>
              <Select id="fr-cause" value={f.invalidity_cause} onChange={set("invalidity_cause")}>
                <option value="">Selecione</option><option value="1">Acidente em serviço</option><option value="2">Moléstia profissional</option>
                <option value="3">Doença grave, contagiosa ou incurável</option><option value="4">Outras</option>
              </Select>
            </FormField>
            <FormField label="CID" htmlFor="fr-cid"><Input id="fr-cid" value={f.cid} onChange={set("cid")} /></FormField>
            <FormField label="Data do laudo médico" htmlFor="fr-laudo" required><Input id="fr-laudo" type="date" value={f.medical_report_date} onChange={set("medical_report_date")} /></FormField>
          </>
        )}
        <FormField label="Fundamento legal da data de validade" htmlFor="fr-vlb" className="sm:col-span-2"><Input id="fr-vlb" value={f.validity_legal_basis} onChange={set("validity_legal_basis")} /></FormField>
        <label className="flex items-center gap-2"><Checkbox checked={f.judicial} onChange={(e) => setF((s) => ({ ...s, judicial: e.target.checked }))} /> Decorre de decisão judicial</label>
        {f.judicial && <FormField label="Nº do processo judicial" htmlFor="fr-jud"><Input id="fr-jud" value={f.judicial_process} onChange={set("judicial_process")} /></FormField>}
        <div className="sm:col-span-2">
          <Button onClick={submit} disabled={busy || (!invalidity && !f.rule) || (lessFavorable && (option.reason.trim().length < 30 || !option.signed))}>
            {busy && <Loader2 className="animate-spin" />} Confirmar enquadramento</Button>
          <span className="ml-3 text-2xs text-muted-foreground">O sistema confere os requisitos na data de validade, compara as regras e guarda a “fotografia” do tempo apurado.</span>
        </div>
      </CardContent>
    </Card>
  );
}

function CalculationCard({ c, canEdit, onSaved }: { c: Concession; canEdit: boolean; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<ParcelRow[]>(c.parcels);
  const [busy, setBusy] = useState(false);
  const calc = c.calculation as Record<string, string | string[] | number | boolean>;
  const memo = c.calculation.memoria as { tabela_fatores: string; competencias_80: number; elevadas_ao_salario_minimo: number; limitadas_ao_teto_rgps: number } | undefined;
  const save = async () => {
    setBusy(true);
    try {
      await api(`concessoes/${c.id}/parcels`, { method: "POST", body: { parcels: rows.map((r) => ({ ...r, amount: String(r.amount).replace(",", ".") })) } });
      toast.success("Parcelas salvas.");
      setEditing(false);
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const upd = (i: number, k: keyof ParcelRow, v: string | boolean) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{c.kind === "PENSAO" ? "Cálculo da pensão e cotas" : "Memória de cálculo e parcelas"}</CardTitle>
        {canEdit && c.kind === "APOSENTADORIA" && !editing && <Button size="sm" variant="outline" onClick={() => { setRows(c.parcels); setEditing(true); }}>Ajustar parcelas</Button>}
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="rounded-md border bg-muted/40 px-3 py-2">
          {c.kind === "PENSAO" && <div><span className="text-muted-foreground">Base: </span>{formatCurrency(String(calc.base))} — {String(calc.base_forma)}</div>}
          <div><span className="text-muted-foreground">Forma: </span>{String(calc.forma ?? "")}</div>
          {calc.data_base ? <div><span className="text-muted-foreground">Data-base (média e tempo): </span>{formatDate(String(calc.data_base))}</div> : null}
          {calc.media100 ? <div><span className="text-muted-foreground">Média 100%: </span>{formatCurrency(String(calc.media100))} · <span className="text-muted-foreground">80% maiores: </span>{calc.media80 ? formatCurrency(String(calc.media80)) : "—"} ({String(calc.competencias)} competências)</div> : null}
          {memo ? <div className="text-2xs text-muted-foreground">Tabela de fatores {memo.tabela_fatores || "—"} · {memo.competencias_80} competências nos 80% maiores · {memo.elevadas_ao_salario_minimo} elevada(s) ao salário mínimo · {memo.limitadas_ao_teto_rgps} limitada(s) ao teto do RGPS (Lei 3.965/2011, art. 62)</div> : null}
          {calc.ultima_remuneracao ? <div><span className="text-muted-foreground">Remuneração do cargo efetivo: </span>{formatCurrency(String(calc.ultima_remuneracao))}{calc.competencia_ultima_remuneracao ? ` (${String(calc.competencia_ultima_remuneracao)})` : ""}</div> : null}
          {calc.observacao ? <div className="text-muted-foreground">{String(calc.observacao)}</div> : null}
          {(calc.avisos as string[] | undefined)?.map((a) => <div key={a} className="text-warning">{a}</div>)}
        </div>

        {c.kind === "APOSENTADORIA" && (
          <Table>
            <TableHeader><TableRow><TableHead>Quadro</TableHead><TableHead>Parcela</TableHead><TableHead>Fundamentação</TableHead><TableHead>Correlação</TableHead><TableHead className="text-right">Valor</TableHead>{editing && <TableHead />}</TableRow></TableHeader>
            <TableBody>
              {(editing ? rows : c.parcels).map((p, i) => (
                <TableRow key={i}>
                  <TableCell>{editing ? <Select value={p.kind} onChange={(e) => upd(i, "kind", e.target.value)}><option value="PROVENTO">Proventos</option><option value="REMUNERACAO">Últ. remuneração</option></Select> : p.kind === "PROVENTO" ? "Proventos" : "Últ. remuneração"}</TableCell>
                  <TableCell>{editing ? <Input value={p.name} onChange={(e) => upd(i, "name", e.target.value)} /> : p.name}</TableCell>
                  <TableCell>{editing ? <Input value={p.legal_basis} onChange={(e) => upd(i, "legal_basis", e.target.value)} /> : p.legal_basis}</TableCell>
                  <TableCell>{editing ? <Input value={p.correlation} onChange={(e) => upd(i, "correlation", e.target.value)} /> : p.correlation}</TableCell>
                  <TableCell className="text-right tabular">{editing ? <Input className="text-right" value={p.amount} onChange={(e) => upd(i, "amount", e.target.value)} /> : formatCurrency(p.amount)}</TableCell>
                  {editing && <TableCell><Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}><Trash2 /></Button></TableCell>}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {editing && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setRows((rs) => [...rs, { kind: "PROVENTO", name: "", legal_basis: "", correlation: "", percent: null, proportionality: null, amount: "0", in_reference: true }])}><Plus /> Parcela</Button>
            <Button size="sm" onClick={save} disabled={busy}>{busy && <Loader2 className="animate-spin" />} Salvar parcelas</Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancelar</Button>
          </div>
        )}

        {c.kind === "PENSAO" && (
          <Table>
            <TableHeader><TableRow><TableHead>Dependente</TableHead><TableHead>Relação</TableHead><TableHead className="text-right">Cota</TableHead><TableHead className="text-right">Valor</TableHead><TableHead>Duração</TableHead></TableRow></TableHeader>
            <TableBody>
              {c.quotas.map((q) => (
                <TableRow key={q.id}>
                  <TableCell><div className="font-medium">{q.dependent_name}</div><div className="text-2xs text-muted-foreground">{q.dependent_cpf}</div></TableCell>
                  <TableCell>{q.relation_display}</TableCell>
                  <TableCell className="text-right tabular">{Number(q.percent).toLocaleString("pt-BR", { maximumFractionDigits: 3 })}%</TableCell>
                  <TableCell className="text-right tabular">{formatCurrency(q.amount)}</TableCell>
                  <TableCell>{q.duration_display}{q.end_date ? ` até ${formatDate(q.end_date)}` : ""}<div className="text-2xs text-muted-foreground">{q.duration_basis}</div></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <div className="text-right text-sm font-semibold">Total: {c.total ? formatCurrency(c.total) : "—"}</div>
      </CardContent>
    </Card>
  );
}

