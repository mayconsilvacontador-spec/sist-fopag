"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import useSWR, { SWRConfig } from "swr";
import { toast } from "sonner";
import {
  AlertCircle, ArrowLeft, Bell, Camera, CheckCircle2, ChevronRight, ClipboardList, Clock, FileText, HelpCircle, IdCard, KeyRound,
  Loader2, Lock, LogOut, MessageSquare, Printer, Receipt, Send, ShieldCheck, User, Wallet,
} from "lucide-react";

import { PayslipBody } from "@/components/folha/payslip";
import { Crest } from "@/components/layout/logo";
import { CameraProblemBox, LiveSelfie, type CameraProblem, type LiveResult } from "@/components/portal/live-selfie";
import { FilePick, RecadForm, useRecadState, type RecadData } from "@/components/recadastramento/form";
import { ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api, fetcher } from "@/lib/api";
import { useBranding } from "@/lib/branding";
import { formatCPF, formatCurrency, formatDate, formatDateTime, maskCPF } from "@/lib/format";
import type { Payslip } from "@/lib/types";
import { cn } from "@/lib/utils";

type Me = {
  must_change_password: boolean;
  instituicao: { nome: string; sigla: string; telefone: string; email: string; site: string };
  pessoa: { nome: string; nome_social: string; cpf: string; nascimento: string; email: string; telefone: string; celular: string };
  endereco: { logradouro: string; numero: string; complemento: string; bairro: string; cidade: string; uf: string; cep: string } | null;
  conta: { banco: string; agencia: string; conta: string } | null;
  dependentes: { nome: string; tipo: string; nascimento: string }[];
  prova_de_vida?: { campanha: string; ato: string; prazo: string; suspenso: boolean; orientacoes: string }[];
};
type Notice = { id: string; nivel: "INFO" | "ATENCAO" | "URGENTE"; titulo: string; mensagem: string; tela: string; lido: boolean; data: string };
type Proof = {
  id: string; campanha: string; ato: string; prazo: string; situacao: "PENDENTE" | "REALIZADA" | "BLOQUEADO" | "DISPENSADA" | "EM_ANALISE";
  situacao_texto: string; realizada_em: string | null; forma: string; orientacoes: string; aceita_portal: boolean;
  campanha_aberta: boolean; motivo_recusa: string; enviada_em: string | null;
};
type Screen = "inicio" | "prova-de-vida" | "recadastramento" | "contracheques" | "informe" | "processos" | "solicitacoes" | "dados" | "senha";

async function logout() {
  await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
  window.location.assign("/segurado/login");
}

export function PortalFrame({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ revalidateOnFocus: false, shouldRetryOnError: false }}>
      <div className="flex min-h-screen flex-col bg-background text-[15px]">{children}</div>
    </SWRConfig>
  );
}

// ------------------------------------------------------------------ cabeçalho com avisos
function Header({ me, onOpen }: { me?: Me; onOpen?: (s: Screen) => void }) {
  const { brasaoUrl } = useBranding(me?.instituicao.sigla);
  return (
    <header className="bg-primary-strong text-white print:hidden">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
        <button type="button" className="flex items-center gap-3 text-left" onClick={() => onOpen?.("inicio")}>
          <Crest url={brasaoUrl} className="h-10 w-10" />
          <div>
            <div className="text-base font-bold">Portal do Segurado</div>
            <div className="text-xs text-white/75">{me?.instituicao.nome ?? "SIST FOPAG"}</div>
          </div>
        </button>
        {me && (
          <div className="flex items-center gap-2">
            {!me.must_change_password && onOpen && <NoticeBell onOpen={onOpen} />}
            <span className="hidden text-sm sm:inline">{(me.pessoa.nome_social || me.pessoa.nome).split(" ")[0]}</span>
            <Button size="sm" variant="outline" className="border-white/30 bg-transparent text-white hover:bg-white/10" onClick={logout}><LogOut /> Sair</Button>
          </div>
        )}
      </div>
    </header>
  );
}

function NoticeBell({ onOpen }: { onOpen: (s: Screen) => void }) {
  const { data, mutate } = useSWR<{ nao_lidos: number; avisos: Notice[] }>("portal/avisos", fetcher, { refreshInterval: 120_000 });
  const [open, setOpen] = useState(false);
  const read = async (n?: Notice) => {
    await api("portal/avisos", { method: "POST", body: n ? { id: n.id } : { todos: true } }).catch(() => undefined);
    mutate();
  };
  return (
    <div className="relative">
      <button type="button" aria-label="Avisos" onClick={() => setOpen(!open)} className="relative rounded-lg p-2 hover:bg-white/10">
        <Bell className="h-5 w-5" />
        {(data?.nao_lidos ?? 0) > 0 && <span className="absolute right-0.5 top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-critical px-1 text-[11px] font-bold">{data!.nao_lidos}</span>}
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-40 w-[330px] overflow-hidden rounded-xl border bg-card text-foreground shadow-xl">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <b className="text-sm">Seus avisos</b>
            {(data?.nao_lidos ?? 0) > 0 && <button type="button" className="text-xs text-primary hover:underline" onClick={() => read()}>Marcar todos como lidos</button>}
          </div>
          <div className="max-h-[360px] overflow-y-auto">
            {data?.avisos.map((n) => (
              <button key={n.id} type="button" onClick={() => { read(n); setOpen(false); if (n.tela) onOpen(n.tela as Screen); }}
                className={cn("block w-full border-b px-4 py-3 text-left last:border-0 hover:bg-muted/60", !n.lido && "bg-primary-soft/60")}>
                <div className={cn("text-sm font-semibold", n.nivel === "URGENTE" ? "text-critical" : n.nivel === "ATENCAO" ? "text-warning" : "text-primary-strong")}>{n.titulo}</div>
                <div className="text-xs text-muted-foreground">{n.mensagem}</div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">{formatDateTime(n.data)}</div>
              </button>
            ))}
            {data?.avisos.length === 0 && <div className="px-4 py-8 text-center text-sm text-muted-foreground">Nenhum aviso por enquanto.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ login
export function PortalLogin() {
  const { branding, brasaoUrl, fundoUrl } = useBranding();
  const [cpf, setCpf] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ portal: true, cpf, password }) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setError(data.detail || "Não foi possível entrar."); return; }
      window.location.assign("/segurado");
    } catch {
      setError("Falha de comunicação com o servidor.");
    } finally {
      setBusy(false);
    }
  };
  const bg = fundoUrl ? { backgroundImage: `linear-gradient(hsl(var(--primary-strong) / 0.55), hsl(var(--primary-strong) / 0.7)), url("${fundoUrl}")`, backgroundSize: "cover", backgroundPosition: "center" } : undefined;
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-10" style={bg}>
      <div className="w-full max-w-[400px]">
        <div className="mb-5 flex flex-col items-center text-center">
          <Crest url={brasaoUrl} className="h-16 w-16" />
          <h1 className={cn("mt-3 text-2xl font-bold", fundoUrl ? "text-white" : "text-primary-strong")}>Portal do Segurado</h1>
          <p className={cn("text-sm", fundoUrl ? "text-white/85" : "text-muted-foreground")}>{branding?.name || "Aposentados, pensionistas e servidores"}</p>
        </div>
        <Card className="rounded-xl p-6 shadow-lg">
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="cpf" className="text-sm">Seu CPF</Label>
              <div className="relative">
                <User className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
                <Input id="cpf" inputMode="numeric" autoComplete="username" autoFocus required value={cpf}
                  onChange={(e) => setCpf(maskCPF(e.target.value))} placeholder="000.000.000-00" className="h-11 pl-10 text-base" />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="password" className="text-sm">Sua senha</Label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
                <Input id="password" type="password" autoComplete="current-password" required value={password}
                  onChange={(e) => setPassword(e.target.value)} className="h-11 pl-10 text-base" />
              </div>
            </div>
            {error && <div className="flex items-start gap-2 rounded-md border border-critical-border bg-critical-soft px-3 py-2 text-sm text-critical" role="alert"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}</div>}
            <Button type="submit" size="lg" className="h-11 w-full text-base" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Entrar</Button>
          </form>
          <div className="mt-4 rounded-lg bg-muted/60 px-3 py-2.5 text-xs text-muted-foreground">
            <b>Primeiro acesso?</b> Peça sua senha provisória no atendimento do instituto. No primeiro acesso o sistema pede para você criar uma senha nova.
          </div>
        </Card>
      </div>
    </main>
  );
}

// ------------------------------------------------------------------ página inicial
const SCREENS: { key: Screen; title: string; text: string; icon: typeof User }[] = [
  { key: "prova-de-vida", title: "Prova de vida", text: "Faça pelo celular, com uma foto sua e do documento.", icon: ShieldCheck },
  { key: "recadastramento", title: "Recadastramento", text: "Confira e atualize seu endereço e seus contatos.", icon: ClipboardList },
  { key: "contracheques", title: "Contracheques", text: "Veja e imprima seus contracheques.", icon: Receipt },
  { key: "informe", title: "Informe de rendimentos", text: "Para a declaração do Imposto de Renda.", icon: FileText },
  { key: "processos", title: "Meus processos", text: "Acompanhe seus pedidos (aposentadoria, pensão, certidões).", icon: Clock },
  { key: "solicitacoes", title: "Fale com o instituto", text: "Atualize dados, peça documentos ou tire dúvidas.", icon: MessageSquare },
  { key: "dados", title: "Meus dados", text: "Dados pessoais, endereço, conta e dependentes.", icon: IdCard },
  { key: "senha", title: "Trocar senha", text: "Crie uma nova senha de acesso.", icon: KeyRound },
];

export function PortalHome() {
  const { data: me, error, mutate } = useSWR<Me>("portal/me", fetcher);
  const [screen, setScreen] = useState<Screen>("inicio");
  useEffect(() => {
    const sync = () => setScreen((window.location.hash.slice(1) as Screen) || "inicio");
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const open = (s: Screen) => { setScreen(s); window.history.replaceState(null, "", s === "inicio" ? "/segurado" : `#${s}`); window.scrollTo(0, 0); };
  if (error) return <><Header /><main className="mx-auto mt-10 max-w-md px-4"><ErrorState error={error} /></main></>;
  if (!me) return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground"><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Carregando…</div>;
  const current = SCREENS.find((s) => s.key === screen);
  return (
    <>
      <Header me={me} onOpen={open} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        {me.must_change_password ? <ChangePassword first onDone={() => mutate()} /> : screen === "inicio" ? <Home me={me} open={open} /> : (
          <>
            <button type="button" onClick={() => open("inicio")} className="mb-3 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline print:hidden">
              <ArrowLeft className="h-4 w-4" /> Voltar ao início
            </button>
            {current && <h1 className="mb-4 flex items-center gap-2 text-2xl font-bold text-primary-strong print:hidden"><current.icon className="h-6 w-6" /> {current.title}</h1>}
            {screen === "prova-de-vida" && <LifeProofScreen />}
            {screen === "recadastramento" && <RecadScreen />}
            {screen === "contracheques" && <Payslips />}
            {screen === "informe" && <Income />}
            {screen === "processos" && <Processes />}
            {screen === "solicitacoes" && <Requests />}
            {screen === "dados" && <MyData me={me} open={open} />}
            {screen === "senha" && <ChangePassword onDone={logout} />}
          </>
        )}
      </main>
      <footer className="border-t bg-card py-3 text-center text-xs text-muted-foreground print:hidden">
        {me.instituicao.nome}{me.instituicao.telefone ? ` · Atendimento: ${me.instituicao.telefone}` : ""}{me.instituicao.email ? ` · ${me.instituicao.email}` : ""}
      </footer>
    </>
  );
}

type BenefitRow = { id: string; tipo: string; modalidade: string; inicio: string; fim: string | null; valor: string; situacao: string; instituidor: string; paridade: boolean; fundamentacao: string };

function Home({ me, open }: { me: Me; open: (s: Screen) => void }) {
  const { data: proofs } = useSWR<Proof[]>("portal/prova-de-vida", fetcher);
  const { data: benefits } = useSWR<BenefitRow[]>("portal/beneficios", fetcher);
  const pending = proofs?.filter((p) => p.campanha_aberta && ["PENDENTE", "BLOQUEADO", "EM_ANALISE"].includes(p.situacao)) ?? [];
  const { data: recad } = useSWR<RecadPortal>("portal/recadastramento", fetcher);
  const recadOpen = recad?.itens.filter((i) => i.campanha_aberta && ["PENDENTE", "DEVOLVIDO", "ENVIADO"].includes(i.situacao)) ?? [];
  const first = (me.pessoa.nome_social || me.pessoa.nome).split(" ")[0];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-primary-strong">Olá, {first}!</h1>
        <p className="text-muted-foreground">O que você precisa hoje? Toque em uma das opções abaixo.</p>
      </div>

      {pending.map((p) => (
        <div key={p.id} className={cn("flex flex-wrap items-center justify-between gap-3 rounded-xl border-2 px-5 py-4",
          p.situacao === "BLOQUEADO" ? "border-critical bg-critical-soft" : p.situacao === "EM_ANALISE" ? "border-info-border bg-info-soft" : "border-warning bg-warning-soft")}>
          <div className="flex items-start gap-3">
            {p.situacao === "EM_ANALISE" ? <Clock className="mt-0.5 h-6 w-6 shrink-0 text-info" /> : <AlertCircle className={cn("mt-0.5 h-6 w-6 shrink-0", p.situacao === "BLOQUEADO" ? "text-critical" : "text-warning")} />}
            <div>
              <div className="text-base font-bold">
                {p.situacao === "BLOQUEADO" ? "Seu benefício está suspenso: faça a prova de vida para voltar a receber"
                  : p.situacao === "EM_ANALISE" ? "Recebemos sua prova de vida — estamos conferindo"
                    : `Faça sua prova de vida até ${formatDate(p.prazo)}`}
              </div>
              <div className="text-sm text-foreground/80">{p.campanha} · {p.ato}{p.motivo_recusa && p.situacao !== "EM_ANALISE" ? ` · Envio anterior não aceito: ${p.motivo_recusa}` : ""}</div>
            </div>
          </div>
          {p.situacao !== "EM_ANALISE" && <Button size="lg" className="h-11 text-base" onClick={() => open("prova-de-vida")}><Camera /> {p.aceita_portal ? "Fazer agora" : "Ver como fazer"}</Button>}
        </div>
      ))}

      {recadOpen.map((r) => (
        <div key={r.id} className={cn("flex flex-wrap items-center justify-between gap-3 rounded-xl border-2 px-5 py-4",
          r.situacao === "DEVOLVIDO" ? "border-critical bg-critical-soft" : r.situacao === "ENVIADO" ? "border-info-border bg-info-soft" : "border-warning bg-warning-soft")}>
          <div className="flex items-start gap-3">
            <ClipboardList className="mt-0.5 h-6 w-6 shrink-0 text-primary" />
            <div>
              <div className="text-base font-bold">{r.situacao === "ENVIADO" ? "Recebemos seu recadastramento — estamos conferindo"
                : r.situacao === "DEVOLVIDO" ? "Seu recadastramento precisa de correção" : `Faça seu recadastramento até ${formatDate(r.prazo)}`}</div>
              <div className="text-sm text-foreground/80">{r.campanha} · {r.ato}{r.motivo_devolucao ? ` · ${r.motivo_devolucao}` : ""}</div>
            </div>
          </div>
          {r.situacao !== "ENVIADO" && <Button size="lg" className="h-11 text-base" onClick={() => open("recadastramento")}>{r.aceita_portal ? "Fazer agora" : "Ver como fazer"}</Button>}
        </div>
      ))}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {SCREENS.map((s) => (
          <button key={s.key} type="button" onClick={() => open(s.key)}
            className="group flex items-start gap-4 rounded-xl border bg-card p-5 text-left shadow-card transition hover:border-primary/40 hover:shadow-md">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary"><s.icon className="h-6 w-6" /></span>
            <span className="min-w-0 flex-1">
              <span className="block text-base font-semibold text-primary-strong">{s.title}</span>
              <span className="block text-sm text-muted-foreground">{s.text}</span>
            </span>
            <ChevronRight className="mt-3 h-5 w-5 shrink-0 text-muted-foreground group-hover:text-primary" />
          </button>
        ))}
      </div>

      {benefits && benefits.length > 0 && (
        <Card className="rounded-xl p-5">
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-primary-strong"><Wallet className="h-5 w-5" /> Meus benefícios</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {benefits.map((b) => (
              <div key={b.id} className="rounded-lg border px-4 py-3">
                <div className="flex items-center justify-between gap-2"><b>{b.tipo}{b.modalidade ? ` — ${b.modalidade}` : ""}</b><Badge variant={b.situacao === "Ativo" ? "success" : "critical"}>{b.situacao}</Badge></div>
                <div className="mt-1 text-2xl font-bold text-primary-strong">{formatCurrency(b.valor)}</div>
                <div className="text-xs text-muted-foreground">Desde {formatDate(b.inicio)}{b.instituidor ? ` · instituidor: ${b.instituidor}` : ""}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function Help({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-info-border bg-info-soft px-4 py-3 text-sm text-info print:hidden">
      <HelpCircle className="mt-0.5 h-4 w-4 shrink-0" /><div className="text-foreground/85">{children}</div>
    </div>
  );
}

// ------------------------------------------------------------------ prova de vida pelo portal
function LifeProofScreen() {
  const { data, mutate } = useSWR<Proof[]>("portal/prova-de-vida", fetcher);
  if (!data) return <Card className="p-6"><Loader2 className="animate-spin" /></Card>;
  const open = data.filter((p) => p.campanha_aberta && ["PENDENTE", "BLOQUEADO"].includes(p.situacao));
  return (
    <div className="space-y-4">
      <Help>A prova de vida confirma que você está vivo(a) e mantém seu benefício em dia. Pelo Portal, basta <b>uma selfie
        segurando seu documento</b> e <b>uma foto do documento</b>. A equipe do instituto confere e você recebe um aviso com o resultado.</Help>
      {open.map((p) => p.aceita_portal ? <ProofWizard key={p.id} p={p} onDone={() => mutate()} /> : (
        <Card key={p.id} className="rounded-xl p-5">
          <div className="text-lg font-semibold text-primary-strong">{p.campanha}</div>
          <p className="text-sm">Prazo: <b>{formatDate(p.prazo)}</b>. Esta campanha precisa ser feita no instituto.</p>
          {p.orientacoes && <p className="mt-2 text-sm text-muted-foreground">{p.orientacoes}</p>}
        </Card>
      ))}
      <Card className="rounded-xl p-5">
        <h2 className="mb-2 text-base font-semibold text-primary-strong">Histórico</h2>
        <div className="divide-y">
          {data.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
              <div><b>{p.campanha}</b><div className="text-xs text-muted-foreground">Prazo {formatDate(p.prazo)}{p.realizada_em ? ` · realizada em ${formatDate(p.realizada_em)}${p.forma ? ` (${p.forma.toLowerCase()})` : ""}` : ""}</div></div>
              <Badge variant={p.situacao === "REALIZADA" || p.situacao === "DISPENSADA" ? "success" : p.situacao === "BLOQUEADO" ? "critical" : p.situacao === "EM_ANALISE" ? "info" : "warning"}>{p.situacao_texto}</Badge>
            </div>
          ))}
          {data.length === 0 && <p className="py-4 text-center text-sm text-muted-foreground">Nenhuma prova de vida aberta para você no momento.</p>}
        </div>
      </Card>
    </div>
  );
}

function PhotoStep({ n, title, tips, capture, file, setFile, cta }: {
  n: number; title: string; tips: string[]; capture: "user" | "environment"; file: File | null; setFile: (f: File | null) => void; cta: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) { setUrl(null); return; }
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return (
    <div className="space-y-3">
      <div className="text-lg font-semibold text-primary-strong">Passo {n} de 3 — {title}</div>
      <ul className="list-disc space-y-0.5 pl-5 text-sm text-muted-foreground">{tips.map((t) => <li key={t}>{t}</li>)}</ul>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" capture={capture} className="hidden"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={title} className="max-h-72 rounded-lg border object-contain" />
      ) : (
        <button type="button" onClick={() => input.current?.click()}
          className="flex h-44 w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-primary/40 bg-primary-soft/40 text-primary hover:bg-primary-soft">
          <Camera className="h-10 w-10" /><span className="text-base font-semibold">{cta}</span>
        </button>
      )}
      {url && <Button variant="outline" onClick={() => input.current?.click()}><Camera /> Tirar outra foto</Button>}
    </div>
  );
}

function ProofWizard({ p, onDone }: { p: Proof; onDone: () => void }) {
  const [step, setStep] = useState(1);
  const [live, setLive] = useState<LiveResult | null>(null);
  const [problem, setProblem] = useState<CameraProblem | null>(null);
  const [alternative, setAlternative] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const selfie = useMemo(() => (live ? new File([live.selfie], "selfie.jpg", { type: "image/jpeg" }) : null), [live]);
  const [doc, setDoc] = useState<File | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const send = async () => {
    if (!selfie || !doc) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("selfie", selfie);
      fd.append("documento", doc);
      fd.append("declaracao", agree ? "true" : "false");
      live!.frames.forEach((f, i) => fd.append("gestos", new File([f], `gesto-${i + 1}.jpg`, { type: "image/jpeg" })));
      fd.append("vivacidade", JSON.stringify(live!.liveness));
      const res = await fetch(`/api/backend/portal/prova-de-vida/${p.id}/enviar`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Não foi possível enviar. Tente de novo.");
      setSent(true);
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (sent) return (
    <Card className="rounded-xl border-success-border p-6 text-center">
      <CheckCircle2 className="mx-auto h-12 w-12 text-success" />
      <div className="mt-2 text-xl font-bold text-success">Prova de vida enviada!</div>
      <p className="text-sm text-muted-foreground">A equipe vai conferir as fotos. Você receberá um aviso aqui no Portal{" "}
        (e no celular, se estiver cadastrado) com o resultado.</p>
    </Card>
  );
  return (
    <Card className="rounded-xl p-5">
      <div className="mb-1 text-sm text-muted-foreground">{p.campanha} · prazo <b>{formatDate(p.prazo)}</b></div>
      {p.situacao === "BLOQUEADO" && <div className="mb-3 rounded-lg bg-critical-soft px-3 py-2 text-sm text-critical">Seu benefício está suspenso. Assim que a prova for aprovada, ele volta a ser pago.</div>}
      {p.motivo_recusa && <div className="mb-3 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">Envio anterior não aceito: {p.motivo_recusa}</div>}
      <div className="mb-4 flex gap-1.5">{[1, 2, 3].map((i) => <div key={i} className={cn("h-1.5 flex-1 rounded-full", i <= step ? "bg-primary" : "bg-muted")} />)}</div>
      {step === 1 && (
        <div className="space-y-3">
          <div className="text-lg font-semibold text-primary-strong">Passo 1 de 3 — Selfie pela câmera</div>
          <ul className="list-disc space-y-0.5 pl-5 text-sm text-muted-foreground">
            <li>Fique em um lugar bem iluminado, sem boné e sem óculos escuros.</li>
            <li>Deixe seu documento (RG ou CNH) por perto: no final você vai segurá-lo ao lado do rosto.</li>
            <li>Por segurança, a selfie é tirada só pela câmera, na hora — não dá para usar foto da galeria.</li>
          </ul>
          {live && !problem ? (
            <div className="space-y-2 text-center">
              <PreviewThumb file={selfie!} label="Selfie tirada agora" />
              <Button variant="outline" onClick={() => { setLive(null); setAttempt(attempt + 1); }}>Tirar de novo</Button>
            </div>
          ) : problem ? (
            <CameraProblemBox problem={problem} onRetry={() => { setProblem(null); setAttempt(attempt + 1); }} onAlternative={() => setAlternative(true)} />
          ) : (
            <LiveSelfie key={attempt} onDone={(r) => { setLive(r); setProblem(null); }} onProblem={setProblem} />
          )}
          {!live && <button type="button" className="text-sm font-medium text-primary underline" onClick={() => setAlternative(true)}>Não consigo usar a câmera — pedir atendimento</button>}
        </div>
      )}
      {step === 2 && <PhotoStep n={2} title="Foto do documento" capture="environment" file={doc} setFile={setDoc} cta="Tirar foto do documento"
        tips={["Coloque o documento sobre uma mesa.", "Fotografe a parte com a sua foto, sem cortar as bordas.", "Confira se dá para ler o nome e o número."]} />}
      {step === 3 && (
        <div className="space-y-3">
          <div className="text-lg font-semibold text-primary-strong">Passo 3 de 3 — Confirmar e enviar</div>
          <div className="grid grid-cols-2 gap-3">
            {[selfie, doc].map((f, i) => f && <PreviewThumb key={i} file={f} label={i === 0 ? "Selfie" : "Documento"} />)}
          </div>
          <label className="flex items-start gap-3 rounded-lg border p-3 text-sm">
            <input type="checkbox" className="mt-1 h-5 w-5" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            <span>Declaro que sou eu na foto, que as imagens foram tiradas agora e que as informações são verdadeiras. Sei que
              declaração falsa é crime (art. 299 do Código Penal).</span>
          </label>
        </div>
      )}
      <div className="mt-5 flex flex-wrap justify-between gap-2">
        <Button variant="outline" size="lg" disabled={step === 1 || busy} onClick={() => setStep(step - 1)}>Voltar</Button>
        {step < 3
          ? <Button size="lg" className="text-base" disabled={(step === 1 && !live) || (step === 2 && !doc)} onClick={() => setStep(step + 1)}>Continuar <ChevronRight /></Button>
          : <Button size="lg" className="text-base" disabled={!agree || busy} onClick={send}>{busy ? <Loader2 className="animate-spin" /> : <Send />} Enviar prova de vida</Button>}
      </div>
      {alternative && <AlternativeDialog p={p} onClose={() => setAlternative(false)} />}
    </Card>
  );
}

/** Para quem não consegue usar a câmera: pede atendimento presencial, visita domiciliar ou por procurador. */
function AlternativeDialog({ p, onClose }: { p: Proof; onClose: () => void }) {
  const [how, setHow] = useState("Atendimento presencial no instituto (agendamento)");
  const [obs, setObs] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      await api("portal/solicitacoes", { method: "POST", body: {
        kind: "REQUERIMENTO", subject: "Prova de vida — atendimento alternativo",
        message: `Não consegui fazer a prova de vida pelo Portal (${p.campanha}, prazo ${formatDate(p.prazo)}). Peço: ${how}.${obs ? ` Observação: ${obs}` : ""}` } });
      setDone(true);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-3 sm:items-center" role="dialog" aria-modal="true">
      <div className="w-full max-w-md space-y-3 rounded-2xl bg-card p-5 shadow-xl">
        {done ? (
          <>
            <CheckCircle2 className="mx-auto h-10 w-10 text-success" />
            <p className="text-center text-base font-semibold">Pedido enviado! O instituto vai entrar em contato para combinar.</p>
            <Button size="lg" className="w-full" onClick={onClose}>Fechar</Button>
          </>
        ) : (
          <>
            <h3 className="text-lg font-bold text-primary-strong">Pedir atendimento para a prova de vida</h3>
            <p className="text-sm text-muted-foreground">Sem câmera ou com dificuldade? Escolha como prefere fazer. O pedido vai direto para a equipe.</p>
            <div className="space-y-2">
              {["Atendimento presencial no instituto (agendamento)", "Visita domiciliar ou hospitalar (estou impossibilitado de ir)", "Prova feita por procurador ou curador"].map((o) => (
                <label key={o} className={cn("flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm", how === o && "border-primary bg-primary-soft")}>
                  <input type="radio" name="alt" checked={how === o} onChange={() => setHow(o)} className="h-5 w-5" /> {o}
                </label>
              ))}
            </div>
            <Textarea value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Observação (opcional): melhor horário, endereço, telefone…" />
            <div className="flex gap-2">
              <Button variant="outline" size="lg" className="flex-1" onClick={onClose} disabled={busy}>Voltar</Button>
              <Button size="lg" className="flex-1" onClick={send} disabled={busy}>{busy && <Loader2 className="animate-spin" />} Enviar pedido</Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function PreviewThumb({ file, label }: { file: File; label: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => { const u = URL.createObjectURL(file); setUrl(u); return () => URL.revokeObjectURL(u); }, [file]);
  return (
    <div className="space-y-1 text-center text-xs text-muted-foreground">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {url && <img src={url} alt={label} className="h-36 w-full rounded-lg border object-cover" />}
      <div>{label}</div>
    </div>
  );
}

// ------------------------------------------------------------------ recadastramento pelo portal
type RecadItem = { id: string; campanha: string; ato: string; prazo: string; situacao: string; situacao_texto: string; motivo_devolucao: string;
  aceita_portal: boolean; campanha_aberta: boolean; exige_comprovante: boolean; orientacoes: string; enviado_em: string | null };
type RecadPortal = { cadastro: RecadData; itens: RecadItem[] };

function RecadScreen() {
  const { data, mutate } = useSWR<RecadPortal>("portal/recadastramento", fetcher);
  if (!data) return <Card className="p-6"><Loader2 className="animate-spin" /></Card>;
  const open = data.itens.filter((i) => i.campanha_aberta && ["PENDENTE", "DEVOLVIDO"].includes(i.situacao));
  return (
    <div className="space-y-4">
      <Help>O recadastramento mantém seus dados em dia (endereço, telefone, estado civil) para o instituto conseguir falar com você e
        pagar seu benefício corretamente. Confira, corrija o que mudou e envie com um comprovante de residência. A equipe confere antes de atualizar.</Help>
      {open.map((i) => i.aceita_portal ? <RecadWizard key={i.id} item={i} cadastro={data.cadastro} onDone={() => mutate()} /> : (
        <Card key={i.id} className="rounded-xl p-5"><div className="text-lg font-semibold text-primary-strong">{i.campanha}</div>
          <p className="text-sm">Prazo: <b>{formatDate(i.prazo)}</b>. Esta campanha é feita no instituto: leve documento com foto e comprovante de residência.</p>
          {i.orientacoes && <p className="mt-2 text-sm text-muted-foreground">{i.orientacoes}</p>}</Card>
      ))}
      <Card className="rounded-xl p-5">
        <h2 className="mb-2 text-base font-semibold text-primary-strong">Histórico</h2>
        <div className="divide-y">
          {data.itens.map((i) => (
            <div key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
              <div><b>{i.campanha}</b><div className="text-xs text-muted-foreground">Prazo {formatDate(i.prazo)}{i.enviado_em ? ` · enviado em ${formatDate(i.enviado_em)}` : ""}</div></div>
              <Badge variant={i.situacao === "APROVADO" ? "success" : i.situacao === "DEVOLVIDO" ? "critical" : i.situacao === "ENVIADO" ? "info" : "warning"}>{i.situacao_texto}</Badge>
            </div>
          ))}
          {data.itens.length === 0 && <p className="py-4 text-center text-sm text-muted-foreground">Nenhum recadastramento aberto para você no momento.</p>}
        </div>
      </Card>
    </div>
  );
}

function RecadWizard({ item, cadastro, onDone }: { item: RecadItem; cadastro: RecadData; onDone: () => void }) {
  const st = useRecadState(cadastro);
  const [step, setStep] = useState(1);
  const [comp, setComp] = useState<File | null>(null);
  const [doc, setDoc] = useState<File | null>(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("dados", JSON.stringify(st.data));
      fd.append("declaracoes", JSON.stringify({ ...st.decl, veracidade: agree }));
      if (comp) fd.append("comprovante", comp);
      if (doc) fd.append("documento", doc);
      const res = await fetch(`/api/backend/portal/recadastramento/${item.id}/enviar`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Não foi possível enviar. Confira os dados e tente de novo.");
      setSent(true);
      onDone();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  if (sent) return (
    <Card className="rounded-xl border-success-border p-6 text-center">
      <CheckCircle2 className="mx-auto h-12 w-12 text-success" />
      <div className="mt-2 text-xl font-bold text-success">Recadastramento enviado!</div>
      <p className="text-sm text-muted-foreground">A equipe vai conferir e você receberá um aviso com o resultado.</p>
    </Card>
  );
  return (
    <Card className="rounded-xl p-5">
      <div className="mb-1 text-sm text-muted-foreground">{item.campanha} · prazo <b>{formatDate(item.prazo)}</b></div>
      {item.motivo_devolucao && <div className="mb-3 rounded-lg bg-critical-soft px-3 py-2 text-sm text-critical">Correção pedida pela equipe: {item.motivo_devolucao}</div>}
      <div className="mb-4 flex gap-1.5">{[1, 2, 3].map((i) => <div key={i} className={cn("h-1.5 flex-1 rounded-full", i <= step ? "bg-primary" : "bg-muted")} />)}</div>
      {step === 1 && <><div className="mb-3 text-lg font-semibold text-primary-strong">Passo 1 de 3 — Confira e atualize seus dados</div>
        <RecadForm large data={st.data} setData={st.setData} decl={st.decl} setDecl={st.setDecl} /></>}
      {step === 2 && (
        <div className="space-y-4">
          <div className="text-lg font-semibold text-primary-strong">Passo 2 de 3 — Comprovante de residência</div>
          <FilePick label={`Comprovante de residência${item.exige_comprovante ? " (obrigatório)" : " (opcional)"}`} file={comp} setFile={setComp}
            hint="Conta de luz, água, gás, telefone ou internet dos últimos 3 meses. Pode tirar uma foto da conta." />
          <FilePick label="Documento com foto (opcional)" file={doc} setFile={setDoc} hint="RG ou CNH — ajuda a equipe a conferir seus dados." />
        </div>
      )}
      {step === 3 && (
        <div className="space-y-3">
          <div className="text-lg font-semibold text-primary-strong">Passo 3 de 3 — Confirmar e enviar</div>
          <div className="rounded-lg bg-muted/60 p-3 text-sm">
            <div><b>Celular:</b> {st.data.pessoa.mobile || "—"} · <b>E-mail:</b> {st.data.pessoa.email || "—"}</div>
            <div><b>Endereço:</b> {st.data.endereco.street}, {st.data.endereco.number || "s/n"} — {st.data.endereco.district} — {st.data.endereco.city}/{st.data.endereco.uf}</div>
            <div><b>Comprovante:</b> {comp?.name ?? "não enviado"}</div>
          </div>
          <label className="flex items-start gap-3 rounded-lg border p-3 text-sm">
            <input type="checkbox" className="mt-1 h-5 w-5" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            <span>Declaro que as informações são verdadeiras e estou ciente de que declaração falsa é crime (art. 299 do Código Penal).</span>
          </label>
        </div>
      )}
      <div className="mt-5 flex flex-wrap justify-between gap-2">
        <Button variant="outline" size="lg" disabled={step === 1 || busy} onClick={() => setStep(step - 1)}>Voltar</Button>
        {step < 3
          ? <Button size="lg" className="text-base" disabled={step === 2 && item.exige_comprovante && !comp} onClick={() => setStep(step + 1)}>Continuar <ChevronRight /></Button>
          : <Button size="lg" className="text-base" disabled={!agree || busy} onClick={send}>{busy ? <Loader2 className="animate-spin" /> : <Send />} Enviar recadastramento</Button>}
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ senha
function ChangePassword({ onDone, first }: { onDone: () => void; first?: boolean }) {
  const [current, setCurrent] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pw !== pw2) { toast.error("A confirmação não confere com a nova senha."); return; }
    setBusy(true);
    try {
      await api("auth/change-password", { method: "POST", body: { current_password: current, new_password: pw } });
      toast.success("Senha alterada. Entre novamente com a nova senha.");
      await logout();
      onDone();
    } catch (err) {
      const fe = err instanceof ApiError ? Object.values(err.fieldErrors).join(" ") : "";
      toast.error(fe || (err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="mx-auto max-w-md rounded-xl p-6">
      <h2 className="mb-1 text-lg font-semibold text-primary-strong">{first ? "Bem-vindo(a)! Crie sua senha" : "Trocar senha"}</h2>
      <p className="mb-4 text-sm text-muted-foreground">{first ? "Por segurança, troque a senha provisória que você recebeu. " : ""}Use ao menos 10 caracteres, misturando letras, números e símbolos. Não conte sua senha a ninguém.</p>
      <form onSubmit={submit} className="space-y-3">
        <FormField label={first ? "Senha provisória" : "Senha atual"} htmlFor="pw0"><Input id="pw0" type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} className="h-11" /></FormField>
        <FormField label="Nova senha" htmlFor="pw1"><Input id="pw1" type="password" required minLength={10} value={pw} onChange={(e) => setPw(e.target.value)} className="h-11" /></FormField>
        <FormField label="Repita a nova senha" htmlFor="pw2"><Input id="pw2" type="password" required value={pw2} onChange={(e) => setPw2(e.target.value)} className="h-11" /></FormField>
        <Button type="submit" size="lg" className="h-11 w-full text-base" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Salvar nova senha</Button>
      </form>
    </Card>
  );
}

// ------------------------------------------------------------------ meus dados
function MyData({ me, open }: { me: Me; open: (s: Screen) => void }) {
  const line = (k: string, v: React.ReactNode) => <div className="flex justify-between gap-3 border-b py-2 last:border-0"><span className="text-muted-foreground">{k}</span><span className="text-right font-medium">{v || "—"}</span></div>;
  return (
    <div className="space-y-4">
      <Help>Encontrou algum dado errado ou desatualizado? <button type="button" className="font-semibold text-primary underline" onClick={() => open("solicitacoes")}>Peça a correção em “Fale com o instituto”</button>.</Help>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="rounded-xl p-5 text-sm">
          <h2 className="mb-2 text-base font-semibold text-primary-strong">Dados pessoais</h2>
          {line("Nome", me.pessoa.nome)}{line("CPF", me.pessoa.cpf)}{line("Nascimento", formatDate(me.pessoa.nascimento))}
          {line("E-mail", me.pessoa.email)}{line("Celular", me.pessoa.celular || me.pessoa.telefone)}
          {line("Endereço", me.endereco ? `${me.endereco.logradouro}, ${me.endereco.numero || "s/n"}${me.endereco.complemento ? " " + me.endereco.complemento : ""} — ${me.endereco.bairro} — ${me.endereco.cidade}/${me.endereco.uf}` : "")}
          {line("Conta de crédito", me.conta ? `${me.conta.banco} · ag. ${me.conta.agencia} · conta ${me.conta.conta}` : "")}
        </Card>
        <Card className="rounded-xl p-5 text-sm">
          <h2 className="mb-2 text-base font-semibold text-primary-strong">Dependentes</h2>
          {me.dependentes.map((d) => line(d.nome, d.tipo))}
          {me.dependentes.length === 0 && <p className="text-muted-foreground">Nenhum dependente cadastrado.</p>}
        </Card>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ contracheques
type SlipRow = { id: string; competencia: string; tipo: string; beneficio: string; bruto: string; descontos: string; liquido: string; pago_em: string | null };

function Payslips() {
  const { data, error } = useSWR<SlipRow[]>("portal/contracheques", fetcher);
  if (error) return <ErrorState error={error} />;
  return (
    <>
      <Help>Toque em <b>Abrir</b> para ver o contracheque completo e imprimir. Aparecem aqui as folhas já fechadas pelo instituto.</Help>
      <Card className="rounded-xl">
        <Table>
          <TableHeader><TableRow><TableHead>Mês</TableHead><TableHead className="hidden sm:table-cell">Benefício</TableHead><TableHead className="text-right">Líquido</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={4} />}
            {data?.map((s) => (
              <TableRow key={s.id}>
                <TableCell className="font-semibold">{s.competencia}{s.tipo !== "Mensal" && <Badge variant="info" className="ml-1">13º</Badge>}</TableCell>
                <TableCell className="hidden text-sm sm:table-cell">{s.beneficio}</TableCell>
                <TableCell className="text-right text-base font-bold tabular">{formatCurrency(s.liquido)}</TableCell>
                <TableCell><Link href={`/segurado/contracheque/${s.id}`}><Button size="sm"><FileText /> Abrir</Button></Link></TableCell>
              </TableRow>
            ))}
            {data?.length === 0 && <TableRow><TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">Nenhum contracheque disponível ainda.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}

// ------------------------------------------------------------------ informe de rendimentos
type Informe = {
  ano_calendario: number; beneficiario: string; cpf: string; fonte_pagadora: { nome: string; cnpj: string };
  quadro_3: Record<string, string>; quadro_4: Record<string, string>; quadro_5: Record<string, string>;
  rra: { rendimento: string; contribuicao: string; irrf: string; meses: number } | null;
};

function Income() {
  const years = useSWR<{ anos: number[] }>("portal/informe-rendimentos", fetcher);
  const [year, setYear] = useState<number | null>(null);
  useEffect(() => { if (years.data?.anos.length && year === null) setYear(years.data.anos[0]); }, [years.data, year]);
  const { data } = useSWR<Informe>(year ? `portal/informe-rendimentos?year=${year}` : null, fetcher);
  const line = (label: string, v?: string) => <div className="flex justify-between border-b py-1.5 last:border-0"><span>{label}</span><span className="tabular font-medium">{formatCurrency(v ?? "0")}</span></div>;
  if (years.data && !years.data.anos.length) return <Card className="rounded-xl p-6 text-center text-sm text-muted-foreground">Ainda não há folhas fechadas para emitir o informe.</Card>;
  return (
    <div className="space-y-3">
      <Help>Use estes valores na sua declaração do Imposto de Renda. Escolha o ano e toque em <b>Imprimir</b> se quiser guardar uma cópia.</Help>
      <div className="flex items-center gap-3 print:hidden">
        <Select className="h-11 w-48" value={year ?? ""} onChange={(e) => setYear(Number(e.target.value))} aria-label="Ano-calendário">
          {years.data?.anos.map((y) => <option key={y} value={y}>Ano-calendário {y}</option>)}
        </Select>
        {data && <Button variant="outline" size="lg" onClick={() => window.print()}><Printer /> Imprimir</Button>}
      </div>
      {data && (
        <Card className="space-y-4 rounded-xl p-5 text-sm">
          <div className="text-center"><div className="text-base font-semibold">Comprovante de Rendimentos Pagos e de Imposto sobre a Renda Retido na Fonte</div><div>Ano-calendário {data.ano_calendario}</div></div>
          <section><div className="section-label mb-1">1. Fonte pagadora</div>{data.fonte_pagadora.nome} · CNPJ {data.fonte_pagadora.cnpj || "—"}</section>
          <section><div className="section-label mb-1">2. Pessoa física beneficiária</div>{data.beneficiario} · CPF {formatCPF(data.cpf)}</section>
          <section><div className="section-label mb-1">3. Rendimentos tributáveis, deduções e imposto retido</div>
            {line("1. Total dos rendimentos", data.quadro_3["1_rendimentos_tributaveis"])}
            {line("2. Contribuição previdenciária oficial", data.quadro_3["2_contribuicao_previdenciaria_oficial"])}
            {line("4. Pensão alimentícia", data.quadro_3["4_pensao_alimenticia"])}
            {line("5. Imposto retido na fonte", data.quadro_3["5_irrf"])}</section>
          <section><div className="section-label mb-1">4. Rendimentos isentos e não tributáveis</div>
            {line("Parcela isenta de aposentadoria/pensão (65 anos ou mais)", data.quadro_4["1_parcela_isenta_65_anos"])}
            {line("Proventos por moléstia grave", data.quadro_4["3_molestia_grave"])}</section>
          <section><div className="section-label mb-1">5. Rendimentos sujeitos à tributação exclusiva</div>
            {line("13º salário", data.quadro_5["1_decimo_terceiro"])}{line("Imposto retido sobre o 13º", data.quadro_5["2_irrf_decimo_terceiro"])}</section>
          {data.rra && <section><div className="section-label mb-1">6. Rendimentos recebidos acumuladamente</div>
            {line(`Rendimentos (${data.rra.meses} meses)`, data.rra.rendimento)}{line("Contribuição", data.rra.contribuicao)}{line("Imposto retido", data.rra.irrf)}</section>}
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ processos
type Proc = { id: string; numero: string; tipo: string; assunto: string; aberto_em: string; situacao: string; setor_atual: string; andamentos: { data: string; tipo: string; setor: string }[] };

function Processes() {
  const { data } = useSWR<Proc[]>("portal/processos", fetcher);
  if (!data) return <Card className="p-4"><Loader2 className="animate-spin" /></Card>;
  return (
    <div className="space-y-3">
      <Help>Aqui você acompanha cada pedido seu no instituto: em que setor está e o que já foi feito.</Help>
      {data.map((p) => (
        <Card key={p.id} className="rounded-xl p-5 text-sm">
          <div className="flex flex-wrap justify-between gap-2"><b className="text-base">Processo {p.numero} — {p.tipo}</b><Badge variant="info">{p.situacao}</Badge></div>
          <div className="text-muted-foreground">{p.assunto} · aberto em {formatDate(p.aberto_em)} · está agora em: <b>{p.setor_atual}</b></div>
          <ol className="mt-3 space-y-1 border-l-2 border-primary/30 pl-4">
            {p.andamentos.map((m, i) => <li key={i}><span className="text-muted-foreground">{formatDateTime(m.data)}</span> — {m.tipo}{m.setor ? ` → ${m.setor}` : ""}</li>)}
          </ol>
        </Card>
      ))}
      {data.length === 0 && <Card className="rounded-xl p-6 text-center text-sm text-muted-foreground">Nenhum processo em seu nome.</Card>}
    </div>
  );
}

// ------------------------------------------------------------------ fale com o instituto
type Req = { id: string; kind: string; kind_display: string; subject: string; message: string; status: string; status_display: string; answer: string; answered_at: string | null; process_code: string; created_at: string };

function Requests() {
  const { data, mutate } = useSWR<Req[]>("portal/solicitacoes", fetcher);
  const [f, setF] = useState({ kind: "ATUALIZACAO", subject: "", message: "" });
  const [busy, setBusy] = useState(false);
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api("portal/solicitacoes", { method: "POST", body: f });
      toast.success("Mensagem enviada! Você será avisado quando o instituto responder.");
      setF({ kind: "ATUALIZACAO", subject: "", message: "" });
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      <Card className="rounded-xl p-5">
        <form onSubmit={send} className="space-y-3">
          <h2 className="text-base font-semibold text-primary-strong">Nova mensagem</h2>
          <FormField label="Sobre o que é?" htmlFor="rq-kind">
            <Select id="rq-kind" className="h-11" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              <option value="ATUALIZACAO">Atualizar meus dados (endereço, telefone, conta)</option>
              <option value="REQUERIMENTO">Pedir um documento ou serviço</option>
              <option value="DUVIDA">Tirar uma dúvida</option>
            </Select>
          </FormField>
          <FormField label="Assunto" htmlFor="rq-subj"><Input id="rq-subj" className="h-11" required maxLength={150} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} placeholder="Ex.: Mudei de endereço" /></FormField>
          <FormField label="Escreva sua mensagem" htmlFor="rq-msg"><Textarea id="rq-msg" required rows={5} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></FormField>
          <Button type="submit" size="lg" className="h-11 w-full text-base" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Send />} Enviar</Button>
        </form>
      </Card>
      <div className="space-y-2">
        <h2 className="text-base font-semibold text-primary-strong">Minhas mensagens</h2>
        {data?.map((r) => (
          <Card key={r.id} className="rounded-xl p-4 text-sm">
            <div className="flex justify-between gap-2"><b>{r.subject}</b><Badge variant={r.status === "RESPONDIDA" ? "success" : "neutral"}>{r.status_display}</Badge></div>
            <div className="text-xs text-muted-foreground">{r.kind_display} · {formatDateTime(r.created_at)}</div>
            <p className="mt-1 whitespace-pre-wrap">{r.message}</p>
            {r.answer && <div className="mt-2 rounded-lg bg-success-soft px-3 py-2"><b>Resposta do instituto:</b> {r.answer}{r.process_code ? ` (processo ${r.process_code})` : ""}</div>}
          </Card>
        ))}
        {data?.length === 0 && <Card className="rounded-xl p-6 text-center text-sm text-muted-foreground">Você ainda não enviou mensagens.</Card>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ contracheque (impressão)
export function PortalPayslip({ id }: { id: string }) {
  const { data: me } = useSWR<Me>("portal/me", fetcher);
  const { data, error } = useSWR<Payslip>(`portal/contracheques/${id}`, fetcher);
  return (
    <>
      <Header me={me} />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-5">
        <div className="mb-3 flex justify-between print:hidden">
          <Link href="/segurado#contracheques" className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"><ArrowLeft className="h-4 w-4" /> Voltar</Link>
          <Button variant="outline" onClick={() => window.print()} disabled={!data}><Printer /> Imprimir</Button>
        </div>
        {error && <ErrorState error={error} />}
        {data && <Card className="p-6 print:border-0 print:p-0 print:shadow-none"><PayslipBody p={data} institutionName={me?.instituicao.nome} /></Card>}
      </main>
    </>
  );
}

