"use client";

/**
 * Leitura inteligente de processos: envie os PDFs (mesmo digitalizados), a IA reconhece cada documento e extrai os
 * dados com a página de origem; a equipe confere ao lado do documento e aplica ao Cadastro Único.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import {
  AlertTriangle, Check, CheckCheck, CircleCheck, Eye, EyeOff, FileSearch, FileUp, KeyRound, Loader2, PlugZap,
  RotateCcw, Sparkles, Trash2, Undo2, XCircle,
} from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, type Paginated } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Settings = {
  motor: "LOCAL" | "ANTHROPIC"; motores: { value: string; label: string }[]; pronto: boolean;
  ativo: boolean; chave_cadastrada: boolean; chave_final: string; modelo: string; modelos: { value: string; label: string }[];
  ciencia_privacidade: boolean; ultimo_teste: string | null; resultado_teste: string; pode_configurar: boolean;
};
type Progress = { total: number; lidos: number; erros: number; situacao: string; tokens_entrada: number; tokens_saida: number; custo_estimado_usd: number; motor: string; paginas: number; paginas_lidas: number };
type Job = { id: string; title: string; engine: string; status: string; status_display: string; person: string | null; person_name: string; created_at: string; created_by_name: string; applied_at: string | null; andamento: Progress };
type Field = { id: string; chave: string; rotulo: string; valor: string; original: string; pagina: number; trecho: string; confianca: "alta" | "media" | "baixa"; confirmado: boolean; ignorado: boolean; caixa?: number[] | null };
type Row = { periodo: string; bruto: number | null; faltas: number | null; licencas: number | null; suspensoes: number | null; outras: number | null; liquido: number | null; pagina: number; corrigido?: boolean; suspeito?: boolean };
type Rub = { codigo: string; descricao: string; referencia: string; valor: string; natureza: string; pagina: number };
type Doc = { id: string; tipo: string; tipo_display: string; titulo: string; pagina_inicial: number; pagina_final: number; legibilidade: string; observacoes: string; campos: Field[]; frequencia: Row[]; rubricas: Rub[] };
type FileRow = { id: string; nome: string; situacao: "PENDENTE" | "LIDO" | "ERRO"; erro: string; documentos: Doc[]; paginas: number; paginas_lidas: number };
type Check = { nivel: "erro" | "aviso" | "ok"; titulo: string; detalhe: string; refs: { arquivo: string; arquivo_id: string; documento: string; pagina: number; campo: string | null }[] };
type JobDetail = Job & { arquivos: FileRow[]; conferencias: Check[]; aplicado: Record<string, string[]> };

const CONF: Record<string, "success" | "warning" | "critical"> = { alta: "success", media: "warning", baixa: "critical" };
const usd = (v: number) => `US$ ${v.toFixed(2)}`;
type Viewer = { file: string; page: number; caixa?: number[] | null };

export function ReadingPage() {
  return <RequirePermission module="concessao.leitura"><Reading /></RequirePermission>;
}

function Reading() {
  const { can } = useSession();
  const router = useRouter();
  const sel = useSearchParams().get("l");
  const settings = useSWR<Settings>("leitura/configuracao", fetcher);
  const jobs = useSWR<Paginated<Job>>("leitura/leituras?page_size=50", fetcher);
  const [showConfig, setShowConfig] = useState(false);
  const open = (id: string) => router.replace(`?l=${id}`);
  const s = settings.data;
  return (
    <>
      <PageHeader title="Leitura inteligente de processos"
        description="Envie os PDFs do processo como chegaram (mesmo digitalizados). A inteligência artificial reconhece cada documento e lê os dados; a equipe só confere ao lado do documento e aplica ao cadastro."
        breadcrumb={[{ label: "Concessão de Benefícios" }, { label: "Leitura inteligente" }]}
        actions={s?.pode_configurar && <Button variant="outline" onClick={() => setShowConfig((v) => !v)}><KeyRound /> Configurar leitura</Button>} />
      {settings.error && <ErrorState error={settings.error} />}
      {s && showConfig && <SettingsCard s={s} onSaved={() => settings.mutate()} />}
      {s && !s.pronto && !s.pode_configurar && <Card className="mb-4"><CardContent className="p-4 text-sm">A leitura por inteligência artificial não está ativa. Peça a quem administra o sistema.</CardContent></Card>}
      {s && <div className="mb-3 text-xs text-muted-foreground">Motor de leitura: <b>{s.motor === "LOCAL" ? "leitura local gratuita (OCR no próprio servidor — nenhum documento sai do computador)" : "inteligência artificial (API da Anthropic)"}</b></div>}
      <div className="grid gap-4 xl:grid-cols-12">
        <div className="space-y-4 xl:col-span-3">
          {s?.pronto && can("concessao.leitura", "incluir") && <NewJob onCreated={(id) => { jobs.mutate(); open(id); }} />}
          <Card>
            <CardHeader><CardTitle>Leituras</CardTitle></CardHeader>
            <div className="divide-y">
              {jobs.data?.results.map((j) => (
                <button key={j.id} type="button" onClick={() => open(j.id)} className={cn("block w-full px-4 py-2.5 text-left hover:bg-muted/50", sel === j.id && "bg-primary-soft")}>
                  <div className="text-[13px] font-semibold text-primary-strong">{j.title}</div>
                  <div className="flex flex-wrap items-center gap-1.5 text-2xs text-muted-foreground">
                    <Badge variant={j.status === "APLICADO" ? "success" : j.status === "CONFERENCIA" ? "warning" : j.status === "LENDO" ? "info" : "neutral"}>{j.status_display}</Badge>
                    {j.andamento.lidos}/{j.andamento.total} arquivo(s) · {formatDateTime(j.created_at)}
                  </div>
                  {j.person_name && <div className="text-2xs">{j.person_name}</div>}
                </button>
              ))}
              {jobs.data?.results.length === 0 && <div className="px-4 py-6 text-center text-xs text-muted-foreground">Nenhuma leitura ainda.</div>}
            </div>
          </Card>
        </div>
        <div className="xl:col-span-9">
          {sel ? <JobView id={sel} onChanged={() => jobs.mutate()} /> : (
            <Card><CardContent className="space-y-2 p-6 text-sm text-muted-foreground">
              <p className="flex items-center gap-2 font-medium text-foreground"><Sparkles className="h-4 w-4 text-primary" /> Como funciona</p>
              <ol className="list-decimal space-y-1 pl-5">
                <li>Envie todos os PDFs do processo (ato, CTC, histórico funcional, contracheques, RG/CPF, requerimento…).</li>
                <li>O sistema reconhece cada documento e lê os dados — inclusive de folhas digitalizadas.</li>
                <li>Confira: cada dado aparece com a página de onde veio. Confirme, corrija ou ignore.</li>
                <li>O sistema confere os documentos entre si (CPF, nascimento, contas da CTC, totais do contracheque).</li>
                <li>Aplique: pessoa, vínculo, averbações, faltas e os arquivos vão para o Cadastro Único.</li>
              </ol>
            </CardContent></Card>
          )}
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ configuração
function SettingsCard({ s, onSaved }: { s: Settings; onSaved: () => void }) {
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [model, setModel] = useState(s.modelo);
  const [engine, setEngine] = useState(s.motor);
  const [ack, setAck] = useState(s.ciencia_privacidade);
  const [busy, setBusy] = useState(false);
  const save = async (enabled?: boolean) => {
    setBusy(true);
    try {
      await api("leitura/configuracao", { method: "POST", body: { engine, api_key: key || undefined, model, privacy_ack: ack, ...(enabled !== undefined ? { enabled } : {}) } });
      toast.success(enabled === undefined ? "Configuração salva." : enabled ? "Leitura inteligente ativada." : "Leitura inteligente desativada.");
      setKey("");
      onSaved();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  const test = async () => {
    setBusy(true);
    try {
      const r = await api<{ resultado: string }>("leitura/configuracao/testar", { method: "POST", body: {} });
      if (r.resultado.startsWith("Falhou")) toast.error(r.resultado); else toast.success(r.resultado);
      onSaved();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  if (!s.pode_configurar) return null;
  return (
    <Card className="mb-4">
      <CardHeader><CardTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> Motor de leitura</CardTitle></CardHeader>
      <CardContent className="grid gap-3 text-xs md:grid-cols-2">
        <FormField label="Como ler os documentos" htmlFor="ai-engine" className="md:col-span-2"
          hint={engine === "LOCAL" ? "Gratuito e sem internet. Lê o texto das folhas digitalizadas; a equipe confere e corrige com a página ao lado." : "Mais precisa (entende tabelas e documentos difíceis), paga por uso com chave da Anthropic."}>
          <Select id="ai-engine" value={engine} onChange={(e) => setEngine(e.target.value as Settings["motor"])}>{s.motores.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}</Select>
        </FormField>
        {engine === "LOCAL" ? (
          <div className="flex gap-2 md:col-span-2"><Button size="sm" onClick={() => save()} disabled={busy}>{busy && <Loader2 className="animate-spin" />} Salvar</Button></div>
        ) : <>
        <FormField label={s.chave_cadastrada ? `Chave de API (cadastrada, final ${s.chave_final}) — preencha só para trocar` : "Chave de API"} htmlFor="ai-key"
          hint="Gerada em console.anthropic.com › API Keys. Fica criptografada no servidor e nunca aparece de novo.">
          <div className="flex gap-1"><Input id="ai-key" type={show ? "text" : "password"} autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-ant-…" />
            <Button type="button" size="icon" variant="ghost" onClick={() => setShow((v) => !v)} aria-label="Mostrar">{show ? <EyeOff /> : <Eye />}</Button></div>
        </FormField>
        <FormField label="Modelo" htmlFor="ai-model" hint="Opus: máxima precisão em documentos difíceis. Sonnet: cerca de metade do custo.">
          <Select id="ai-model" value={model} onChange={(e) => setModel(e.target.value)}>{s.modelos.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}</Select>
        </FormField>
        <label className="flex items-start gap-2 md:col-span-2">
          <input type="checkbox" className="mt-0.5 h-4 w-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>Estou ciente de que os documentos (com dados pessoais) são enviados à Anthropic para leitura, nos termos do contrato da API, e de que o órgão deve informar esse tratamento aos segurados (LGPD). Os dados lidos só vão ao cadastro depois da conferência da equipe.</span>
        </label>
        {s.ultimo_teste && <div className="md:col-span-2 text-muted-foreground">Último teste ({formatDateTime(s.ultimo_teste)}): {s.resultado_teste}</div>}
        <div className="flex flex-wrap gap-2 md:col-span-2">
          {s.chave_cadastrada && s.ativo && <Button size="sm" onClick={() => save()} disabled={busy}>{busy && <Loader2 className="animate-spin" />} Salvar</Button>}
          {s.chave_cadastrada && <Button size="sm" variant="outline" onClick={test} disabled={busy}><PlugZap /> Testar chave</Button>}
          {!s.ativo && <Button size="sm" onClick={() => save(true)} disabled={busy || !ack || (!s.chave_cadastrada && !key)}>{busy && <Loader2 className="animate-spin" />} Salvar e ativar a IA</Button>}
        </div>
        </>}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ nova leitura
function NewJob({ onCreated }: { onCreated: (id: string) => void }) {
  const [title, setTitle] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const add = (list: FileList | null) => setFiles((cur) => [...cur, ...Array.from(list ?? []).filter((f) => f.name.toLowerCase().endsWith(".pdf"))]);
  const send = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("titulo", title || files[0]?.name.replace(/\.pdf$/i, "") || "Processo");
      files.forEach((f) => fd.append("arquivos", f));
      const res = await fetch("/api/backend/leitura/leituras", { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Falha ao enviar os arquivos.");
      setFiles([]);
      setTitle("");
      onCreated(body.id);
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card>
      <CardHeader><CardTitle>Nova leitura</CardTitle></CardHeader>
      <CardContent className="space-y-2 text-xs">
        <Input placeholder="Descrição (ex.: Processo 158/2025 — aposentadoria)" value={title} onChange={(e) => setTitle(e.target.value)} />
        <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
          onClick={() => input.current?.click()}
          className={cn("cursor-pointer rounded-md border-2 border-dashed p-4 text-center text-muted-foreground", drag && "border-primary bg-primary-soft")}>
          <FileUp className="mx-auto mb-1 h-5 w-5" />Arraste os PDFs aqui ou clique para escolher
          <input ref={input} type="file" accept=".pdf,application/pdf" multiple className="hidden" onChange={(e) => add(e.target.files)} />
        </div>
        {files.length > 0 && <ul className="max-h-40 space-y-0.5 overflow-auto">{files.map((f, i) => (
          <li key={i} className="flex justify-between gap-2"><span className="truncate">{f.name}</span>
            <button type="button" className="text-muted-foreground hover:text-critical" onClick={() => setFiles((c) => c.filter((_, j) => j !== i))} aria-label="Remover">×</button></li>))}</ul>}
        <Button className="w-full" onClick={send} disabled={busy || !files.length}>{busy ? <Loader2 className="animate-spin" /> : <FileSearch />} Ler {files.length || ""} arquivo(s)</Button>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ leitura: andamento, conferência e aplicação
function JobView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { can } = useSession();
  const { data, error, mutate } = useSWR<JobDetail>(`leitura/leituras/${id}`, fetcher);
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [reading, setReading] = useState(false);
  const running = useRef(false);

  const runQueue = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    setReading(true);
    try {
      for (;;) {
        const p = await api<Progress>(`leitura/leituras/${id}/ler`, { method: "POST", body: {} });
        await mutate();
        if (p.situacao !== "LENDO") { onChanged(); break; }
      }
    } catch (err) { toast.error((err as Error).message); } finally { running.current = false; setReading(false); }
  }, [id, mutate, onChanged]);

  useEffect(() => { if (data?.status === "LENDO" && can("concessao.leitura", "incluir")) runQueue(); }, [data?.status, runQueue, can]);
  useEffect(() => { setViewer(null); }, [id]);

  if (error) return <ErrorState error={error} />;
  if (!data) return <Card><CardContent className="p-6"><Loader2 className="animate-spin" /></CardContent></Card>;
  const p = data.andamento;
  const bar = p.motor === "LOCAL" && p.paginas ? (100 * p.paginas_lidas) / p.paginas : p.total ? (100 * p.lidos) / p.total : 0;
  const editable = data.status === "CONFERENCIA" && can("concessao.leitura", "editar");
  const pending = data.arquivos.flatMap((f) => f.documentos.flatMap((d) => d.campos)).filter((c) => !c.confirmado && !c.ignorado).length;
  const act = async (path: string, body: object = {}) => {
    try { await api(`leitura/leituras/${id}/${path}`, { method: "POST", body }); await mutate(); onChanged(); } catch (err) { toast.error((err as Error).message); }
  };
  const showPage = (file: string, page: number, caixa?: number[] | null) => setViewer({ file, page, caixa });

  return (
    <div className={cn("grid gap-4", viewer && "2xl:grid-cols-2")}>
      <div className="min-w-0 space-y-4">
        <Card>
          <CardHeader className="flex-wrap gap-2"><CardTitle>{data.title}</CardTitle>
            <div className="flex items-center gap-2"><Badge variant={data.status === "APLICADO" ? "success" : data.status === "CONFERENCIA" ? "warning" : "info"}>{data.status_display}</Badge>
              {data.status !== "APLICADO" && data.status !== "DESCARTADO" && can("concessao.leitura", "editar") &&
                <Button size="sm" variant="ghost" onClick={() => act("descartar")}><Trash2 /> Descartar</Button>}</div>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all" style={{ width: `${bar}%` }} /></div>
            <div className="flex flex-wrap gap-x-4 text-muted-foreground">
              <span>{p.lidos} de {p.total} arquivo(s) lido(s){p.erros ? ` · ${p.erros} com erro` : ""}{p.motor === "LOCAL" && p.paginas ? ` · ${p.paginas_lidas} de ${p.paginas} página(s)` : ""}</span>
              {p.motor === "LOCAL" ? <span>Leitura local: <b>sem custo</b></span>
                : <span>Custo estimado da leitura: <b>{usd(p.custo_estimado_usd)}</b> ({(p.tokens_entrada / 1000).toFixed(0)} mil tokens lidos)</span>}
              {reading && <span className="flex items-center gap-1 text-primary"><Loader2 className="h-3 w-3 animate-spin" /> lendo… {p.motor === "LOCAL" ? "(cada folha digitalizada leva de 10 a 40 s)" : "(cada arquivo leva de 20 s a 2 min)"}</span>}
            </div>
            {data.status === "LENDO" && !reading && <Button size="sm" onClick={runQueue}><RotateCcw /> Continuar leitura</Button>}
          </CardContent>
        </Card>

        {data.conferencias.length > 0 && (
          <Card>
            <CardHeader><CardTitle>Conferências automáticas</CardTitle>
              {editable && pending > 0 && <Button size="sm" variant="outline" onClick={() => act("confirmar-alta")}><CheckCheck /> Confirmar os de confiança alta</Button>}</CardHeader>
            <CardContent className="space-y-1 text-xs">
              {data.conferencias.map((c, i) => (
                <div key={i} className={cn("flex items-start gap-2 rounded px-2 py-1", c.nivel === "erro" && "bg-critical-soft", c.nivel === "aviso" && "bg-warning-soft")}>
                  {c.nivel === "erro" ? <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" /> : c.nivel === "aviso" ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" /> : <CircleCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />}
                  <div><b>{c.titulo}</b>{c.detalhe && <> — {c.detalhe}</>}
                    {c.refs.length > 0 && <div className="flex flex-wrap gap-x-2 text-2xs">{c.refs.slice(0, 6).map((r, j) => (
                      <button key={j} type="button" className="text-primary underline" onClick={() => showPage(r.arquivo_id, r.pagina)}>{r.documento} p.{r.pagina}</button>))}</div>}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {data.arquivos.map((f) => (
          <Card key={f.id}>
            <CardHeader className="flex-wrap gap-2">
              <CardTitle className="truncate">{f.nome}</CardTitle>
              <div className="flex items-center gap-2">
                {f.situacao === "PENDENTE" && <Badge variant="info">Na fila</Badge>}
                {f.situacao === "ERRO" && <Badge variant="critical">Erro</Badge>}
                {f.situacao !== "PENDENTE" && can("concessao.leitura", "incluir") && (data.status === "CONFERENCIA" || data.status === "LENDO") &&
                  <Button size="sm" variant="outline" title="Lê o arquivo de novo (as conferências feitas neste arquivo são refeitas)"
                    onClick={async () => { await act(`arquivo/${f.id}/reler`); runQueue(); }}><RotateCcw /> Ler de novo</Button>}
                <Button size="sm" variant="ghost" onClick={() => showPage(f.id, 1)}><Eye /> Ver PDF</Button>
              </div>
            </CardHeader>
            {f.erro && <CardContent className="pb-2 text-xs text-critical">{f.erro}</CardContent>}
            {f.documentos.map((d) => <DocBlock key={d.id} job={id} file={f.id} d={d} editable={editable} onPage={showPage} onChanged={() => mutate()} />)}
          </Card>
        ))}

        {editable && <ApplyCard job={data} pending={pending} onDone={() => { mutate(); onChanged(); }} />}
        {data.status === "APLICADO" && <AppliedCard job={data} />}
      </div>
      {viewer && (
        <Card className="2xl:sticky 2xl:top-2 2xl:self-start">
          <CardHeader><CardTitle>Documento — página {viewer.page}</CardTitle><Button size="sm" variant="ghost" onClick={() => setViewer(null)}>Fechar</Button></CardHeader>
          {viewer.caixa ? (
            <div className="max-h-[80vh] overflow-auto border-t">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img alt="Trecho do documento com o dado destacado" className="w-full"
                src={`/api/backend/leitura/leituras/${id}/arquivo/${viewer.file}/pagina/${viewer.page}?caixa=${viewer.caixa.map((v) => v.toFixed(1)).join(",")}`} />
              <div className="p-2 text-2xs text-muted-foreground">O retângulo vermelho mostra de onde o dado foi lido. <button type="button" className="text-primary underline" onClick={() => setViewer({ ...viewer, caixa: null })}>Ver a página inteira</button></div>
            </div>
          ) : (
            <iframe key={`${viewer.file}-${viewer.page}`} title="Documento" className="h-[80vh] w-full border-t"
              src={`/api/backend/leitura/leituras/${id}/arquivo/${viewer.file}#page=${viewer.page}&zoom=page-width`} />
          )}
        </Card>
      )}
    </div>
  );
}

function DocBlock({ job, file, d, editable, onPage, onChanged }: { job: string; file: string; d: Doc; editable: boolean; onPage: (f: string, p: number, caixa?: number[] | null) => void; onChanged: () => void }) {
  return (
    <div className="border-t">
      <div className="flex flex-wrap items-center gap-2 bg-muted/40 px-4 py-1.5 text-xs">
        <b>{d.tipo_display}</b><span className="text-muted-foreground">{d.titulo}</span>
        <button type="button" className="text-primary underline" onClick={() => onPage(file, d.pagina_inicial)}>p. {d.pagina_inicial}{d.pagina_final > d.pagina_inicial ? `–${d.pagina_final}` : ""}</button>
        {d.legibilidade !== "boa" && <Badge variant="warning">legibilidade {d.legibilidade}</Badge>}
      </div>
      {d.observacoes && <div className="px-4 py-1 text-2xs text-muted-foreground">{d.observacoes}</div>}
      {d.campos.length > 0 && (
        <Table>
          <TableHeader><TableRow><TableHead className="w-1/4">Dado</TableHead><TableHead>Valor lido</TableHead><TableHead className="w-16">Pág.</TableHead><TableHead className="w-20">Confiança</TableHead><TableHead className="w-28" /></TableRow></TableHeader>
          <TableBody>{d.campos.map((c) => <FieldRow key={c.id} job={job} file={file} c={c} editable={editable} onPage={onPage} onChanged={onChanged} />)}</TableBody>
        </Table>
      )}
      {d.frequencia.length > 0 && (
        <div className="px-4 py-2">
          <div className="mb-1 text-2xs font-semibold uppercase text-muted-foreground">Frequência lida da certidão{editable ? " — corrija as células que não baterem com a página (clique no ano para ver)" : ""}</div>
          <Table>
            <TableHeader><TableRow><TableHead>Período</TableHead><TableHead className="text-right">Bruto</TableHead><TableHead className="text-right">Faltas</TableHead><TableHead className="text-right">Licenças</TableHead><TableHead className="text-right">Susp.</TableHead><TableHead className="text-right">Outras</TableHead><TableHead className="text-right">Líquido</TableHead></TableRow></TableHeader>
            <TableBody>{d.frequencia.map((r, i) => (
              <TableRow key={i} className={cn(r.corrigido && "bg-success-soft/40", r.suspeito && !r.corrigido && "bg-warning-soft")}
                title={r.suspeito && !r.corrigido ? "Leitura duvidosa: o sistema ajustou pelo valor mais provável. Confira com a página." : undefined}>
                <TableCell><button type="button" className="text-primary underline" onClick={() => onPage(file, r.pagina)}>{r.periodo}</button>
                  {r.suspeito && !r.corrigido && editable && <ConfirmRow job={job} doc={d.id} index={i} value={r.liquido} onChanged={onChanged} />}</TableCell>
                {(["bruto", "faltas", "licencas", "suspensoes", "outras", "liquido"] as const).map((k) => (
                  <TableCell key={k} className="text-right tabular">{editable
                    ? <CellInput job={job} doc={d.id} index={i} column={k} value={r[k]} onChanged={onChanged} />
                    : (r[k] ?? "—")}</TableCell>))}</TableRow>))}
              <TableRow><TableCell className="font-semibold">Soma</TableCell>{(["bruto", "faltas", "licencas", "suspensoes", "outras", "liquido"] as const).map((k) => <TableCell key={k} className="text-right font-semibold tabular">{d.frequencia.reduce((s, r) => s + (r[k] ?? 0), 0)}</TableCell>)}</TableRow>
            </TableBody>
          </Table>
        </div>
      )}
      {d.rubricas.length > 0 && (
        <div className="px-4 py-2">
          <div className="mb-1 text-2xs font-semibold uppercase text-muted-foreground">Rubricas</div>
          <Table>
            <TableHeader><TableRow><TableHead>Código</TableHead><TableHead>Descrição</TableHead><TableHead>Ref.</TableHead><TableHead>Natureza</TableHead><TableHead className="text-right">Valor</TableHead></TableRow></TableHeader>
            <TableBody>{d.rubricas.map((r, i) => (
              <TableRow key={i}><TableCell>{r.codigo}</TableCell><TableCell>{r.descricao}</TableCell><TableCell>{r.referencia}</TableCell><TableCell>{r.natureza}</TableCell><TableCell className="text-right tabular">{r.valor}</TableCell></TableRow>))}</TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function ConfirmRow({ job, doc, index, value, onChanged }: { job: string; doc: string; index: number; value: number | null; onChanged: () => void }) {
  const confirm = async () => {
    try { await api(`leitura/leituras/${job}/linha`, { method: "POST", body: { documento: doc, indice: index, coluna: "liquido", valor: value ?? 0 } }); onChanged(); }
    catch (err) { toast.error((err as Error).message); }
  };
  return <button type="button" className="ml-2 rounded border border-warning-border px-1 text-2xs text-warning hover:bg-warning-soft" onClick={confirm} title="Os valores desta linha conferem com a página">confirmar</button>;
}

function CellInput({ job, doc, index, column, value, onChanged }: { job: string; doc: string; index: number; column: string; value: number | null; onChanged: () => void }) {
  const [v, setV] = useState(value === null ? "" : String(value));
  useEffect(() => setV(value === null ? "" : String(value)), [value]);
  const save = async () => {
    if (v === (value === null ? "" : String(value))) return;
    try { await api(`leitura/leituras/${job}/linha`, { method: "POST", body: { documento: doc, indice: index, coluna: column, valor: v } }); onChanged(); }
    catch (err) { toast.error((err as Error).message); }
  };
  return <Input className={cn("ml-auto h-7 w-16 text-right text-xs", value === null && "border-warning")} inputMode="numeric" value={v}
    onChange={(e) => setV(e.target.value.replace(/\D/g, ""))} onBlur={save} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />;
}

function FieldRow({ job, file, c, editable, onPage, onChanged }: { job: string; file: string; c: Field; editable: boolean; onPage: (f: string, p: number, caixa?: number[] | null) => void; onChanged: () => void }) {
  const [value, setValue] = useState(c.valor);
  const [busy, setBusy] = useState(false);
  useEffect(() => setValue(c.valor), [c.valor]);
  const send = async (body: object) => {
    setBusy(true);
    try { await api(`leitura/leituras/${job}/campo`, { method: "POST", body: { campo: c.id, ...body } }); onChanged(); }
    catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  const changed = value !== c.valor;
  return (
    <TableRow className={cn(c.ignorado && "opacity-50", c.confirmado && !c.ignorado && "bg-success-soft/40")}>
      <TableCell className="text-xs"><div className="font-medium">{c.rotulo}</div>{c.trecho && c.trecho !== c.valor && <div className="text-2xs text-muted-foreground" title="Trecho do documento">“{c.trecho.slice(0, 80)}”</div>}</TableCell>
      <TableCell>{editable && !c.ignorado
        ? <Input className="h-7 text-xs" value={value} onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && changed) send({ valor: value }); }} />
        : <span className="text-xs">{c.valor}</span>}
        {c.original !== c.valor && <div className="text-2xs text-muted-foreground">lido: {c.original}</div>}</TableCell>
      <TableCell><button type="button" className="text-xs text-primary underline" title={c.caixa ? "Ver o trecho destacado" : "Ver a página"} onClick={() => onPage(file, c.pagina, c.caixa)}>{c.pagina}{c.caixa ? " 🔍" : ""}</button></TableCell>
      <TableCell><Badge variant={CONF[c.confianca]}>{c.confianca}</Badge></TableCell>
      <TableCell className="text-right">{editable && (
        <div className="flex justify-end gap-0.5">
          {changed ? <Button size="sm" disabled={busy} onClick={() => send({ valor: value })}>Salvar</Button> : !c.ignorado && (
            <Button size="icon" variant={c.confirmado ? "default" : "outline"} title={c.confirmado ? "Conferido" : "Confirmar"} disabled={busy} onClick={() => send({ confirmar: !c.confirmado })}><Check /></Button>)}
          <Button size="icon" variant="ghost" title={c.ignorado ? "Voltar a usar" : "Ignorar este dado"} disabled={busy} onClick={() => send({ ignorar: !c.ignorado })}>{c.ignorado ? <Undo2 /> : <XCircle />}</Button>
        </div>)}
      </TableCell>
    </TableRow>
  );
}

function ApplyCard({ job, pending, onDone }: { job: JobDetail; pending: number; onDone: () => void }) {
  const organs = useSWR<Paginated<{ id: string; name: string }>>("organs?page_size=200", fetcher);
  const ctcs = useMemo(() => job.arquivos.flatMap((f) => f.documentos.filter((d) => d.tipo === "CTC").map((d) => ({ d, file: f.nome }))), [job]);
  const hasSex = job.arquivos.some((f) => f.documentos.some((d) => d.campos.some((c) => c.chave === "pessoa.sexo" && !c.ignorado)));
  const [organ, setOrgan] = useState("");
  const [massa, setMassa] = useState("PREVIDENCIARIO");
  const [sexo, setSexo] = useState("");
  const [use, setUse] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const errors = job.conferencias.filter((c) => c.nivel === "erro").length;
  const apply = async () => {
    setBusy(true);
    try {
      await api(`leitura/leituras/${job.id}/aplicar`, { method: "POST", body: { orgao: organ || undefined, massa, sexo: sexo || undefined, ctc: use } });
      toast.success("Dados aplicados ao Cadastro Único.");
      onDone();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card>
      <CardHeader><CardTitle>Aplicar ao cadastro</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="grid gap-3 md:grid-cols-3">
          <FormField label="Órgão do vínculo" htmlFor="ap-organ" hint="Necessário para incluir o vínculo (se ainda não existir).">
            <Select id="ap-organ" value={organ} onChange={(e) => setOrgan(e.target.value)}><option value="">Não incluir vínculo</option>{organs.data?.results.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select>
          </FormField>
          <FormField label="Massa (fundo)" htmlFor="ap-massa">
            <Select id="ap-massa" value={massa} onChange={(e) => setMassa(e.target.value)}><option value="PREVIDENCIARIO">Previdenciário</option><option value="FINANCEIRO">Financeiro</option><option value="COMPRA_VIDAS">Compra de Vidas</option></Select>
          </FormField>
          {!hasSex && <FormField label="Sexo (não consta dos documentos)" htmlFor="ap-sexo">
            <Select id="ap-sexo" value={sexo} onChange={(e) => setSexo(e.target.value)}><option value="">Selecione…</option><option value="F">Feminino</option><option value="M">Masculino</option></Select>
          </FormField>}
        </div>
        {ctcs.length > 0 && (
          <div className="space-y-1">
            <div className="font-semibold">Como usar cada CTC</div>
            {ctcs.map(({ d, file }) => (
              <div key={d.id} className="flex flex-wrap items-center gap-2">
                <span className="min-w-56 truncate">{file} — {d.campos.find((c) => c.chave === "ctc.orgao_emissor")?.valor || d.titulo}</span>
                <Select className="h-8 w-80" value={use[d.id] ?? "IGNORAR"} onChange={(e) => setUse((u) => ({ ...u, [d.id]: e.target.value }))}>
                  <option value="IGNORAR">Não usar</option>
                  <option value="AVERBACAO">Averbar (tempo de outro órgão / INSS)</option>
                  <option value="VINCULO">Frequência do próprio vínculo (lança as faltas)</option>
                </Select>
              </div>
            ))}
          </div>
        )}
        <p className="text-muted-foreground">Nada já cadastrado é sobrescrito: só campos vazios são completados e as diferenças ficam listadas. Os PDFs vão para os documentos da pessoa.</p>
        <Button onClick={apply} disabled={busy || pending > 0 || errors > 0}>{busy && <Loader2 className="animate-spin" />} Aplicar ao Cadastro Único</Button>
        {(pending > 0 || errors > 0) && <span className="ml-2 text-warning">{pending > 0 ? `${pending} dado(s) sem conferência` : ""}{pending > 0 && errors > 0 ? " · " : ""}{errors > 0 ? `${errors} divergência(s) a resolver` : ""}</span>}
      </CardContent>
    </Card>
  );
}

function AppliedCard({ job }: { job: JobDetail }) {
  const labels: Record<string, string> = { pessoa: "Pessoa", vinculo: "Vínculo", averbacoes: "Averbações", frequencia: "Frequência", documentos: "Documentos anexados", divergencias: "Diferenças com o cadastro (não alteradas)" };
  return (
    <Card>
      <CardHeader><CardTitle>Aplicado ao cadastro{job.person_name ? ` — ${job.person_name}` : ""}</CardTitle></CardHeader>
      <Table><TableBody>
        {Object.entries(job.aplicado).filter(([, v]) => v.length).map(([k, v]) => (
          <TableRow key={k}><TableCell className="w-48 font-medium">{labels[k] ?? k}</TableCell><TableCell className="text-xs">{v.join(" · ")}</TableCell></TableRow>))}
        {Object.values(job.aplicado).every((v) => !v.length) && <EmptyRow cols={2} text="Nada aplicado." />}
      </TableBody></Table>
      {job.person && <CardContent className="pt-3"><a className="text-xs text-primary underline" href={`/cadastros/pessoas/${job.person}`}>Abrir no Cadastro Único</a> · Abra a concessão a partir do Protocolo normalmente.</CardContent>}
    </Card>
  );
}
