"use client";

/**
 * Processo DIGITALIZADO (backend: apps/leitura/implantacao.py).
 * OrganizeCard — pessoa da leitura, juntar leituras do mesmo processo e acrescentar PDFs.
 * ImplantCard — com a leitura aplicada, implanta na folha a aposentadoria JÁ CONCEDIDA (sem retroativo indevido)
 * e deixa a concessão pronta para a Ficha FATIMA e o COMPREV.
 */
import { useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { CheckCircle2, FilePlus2, Layers, Loader2, Rocket, UserSearch } from "lucide-react";

import { PersonPicker } from "@/components/people/person-picker";
import { useSession } from "@/components/providers/session-provider";
import { FormField } from "@/components/shared/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox, Input, Select } from "@/components/ui/input";
import { api, fetcher, type Paginated } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { PersonRow } from "@/lib/types";

type JobLite = { id: string; title: string; status: string; status_display: string; person: string | null; person_name: string; created_at: string; concession: string | null };

const MODALIDADES = [
  { value: 1, label: "Por idade" }, { value: 2, label: "Por tempo de contribuição" }, { value: 3, label: "Compulsória" },
  { value: 4, label: "Por incapacidade permanente (invalidez)" }, { value: 5, label: "De professor" },
  { value: 6, label: "Especial — atividade de risco" }, { value: 7, label: "Especial — agentes nocivos" },
];

export function OrganizeCard({ job, onChanged }: { job: JobLite; onChanged: () => void }) {
  const { can } = useSession();
  const list = useSWR<Paginated<JobLite>>("leitura/leituras?page_size=100", fetcher);
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  if (!can("concessao.leitura", "editar")) return null;
  const outras = (list.data?.results ?? []).filter((j) => j.id !== job.id && (j.status === "LENDO" || j.status === "CONFERENCIA"));

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try { await fn(); toast.success(ok); onChanged(); list.mutate(); } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  const juntar = () => run(() => api(`leitura/leituras/${job.id}/juntar`, { method: "POST", body: { leituras: sel } }),
    `${sel.length} leitura(s) juntada(s) nesta. Nada foi lido de novo.`).then(() => setSel([]));
  const escolher = (p: PersonRow | null) => {
    setPerson(p);
    run(() => api(`leitura/leituras/${job.id}/pessoa`, { method: "POST", body: { pessoa: p?.id ?? null } }),
      p ? `Leitura ligada a ${p.name}.` : "Pessoa retirada da leitura.");
  };
  const acrescentar = async () => {
    const files = fileRef.current?.files;
    if (!files?.length) return;
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("arquivos", f));
    await run(async () => {
      const r = await fetch(`/api/backend/leitura/leituras/${job.id}/arquivos`, { method: "POST", body: fd, credentials: "same-origin" });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Falha ao enviar os PDFs.");
    }, `${files.length} PDF(s) acrescentado(s): a leitura continua sozinha.`);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <Card>
      <CardHeader><CardTitle>Organizar o processo</CardTitle></CardHeader>
      <CardContent className="space-y-4 text-xs">
        <p className="text-muted-foreground">Um processo = uma leitura. Assim o sistema cruza os documentos entre si (CPF, nome, nascimento, CTC) e todo PDF vai para a pasta da pessoa certa.</p>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1 font-semibold"><UserSearch className="h-4 w-4" /> Pessoa desta leitura</div>
            <div className="text-muted-foreground">{job.person_name ? <>Ligada a <b>{job.person_name}</b>.</> : "Use quando os documentos não trazem CPF (ou a pessoa já está cadastrada)."}</div>
            <PersonPicker value={person} onChange={escolher} />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-1 font-semibold"><Layers className="h-4 w-4" /> Juntar outras leituras deste processo</div>
            <div className="max-h-40 space-y-1 overflow-y-auto rounded border p-2 thin-scroll">
              {outras.map((j) => (
                <label key={j.id} className="flex items-start gap-2">
                  <Checkbox checked={sel.includes(j.id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, j.id] : s.filter((x) => x !== j.id)))} />
                  <span><span className="font-medium">{j.title}</span><span className="block text-2xs text-muted-foreground">{j.status_display} · {formatDateTime(j.created_at)}{j.person_name ? ` · ${j.person_name}` : ""}</span></span>
                </label>
              ))}
              {outras.length === 0 && <div className="text-muted-foreground">Nenhuma outra leitura em aberto.</div>}
            </div>
            <Button size="sm" variant="outline" disabled={busy || sel.length === 0} onClick={juntar}>{busy ? <Loader2 className="animate-spin" /> : <Layers />} Juntar {sel.length || ""} nesta leitura</Button>
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-1 font-semibold"><FilePlus2 className="h-4 w-4" /> Acrescentar PDFs</div>
            <div className="text-muted-foreground">Documentos que faltaram (ex.: contracheque de inativo mais recente, portaria, publicação).</div>
            <Input ref={fileRef} type="file" accept="application/pdf" multiple className="py-1" />
            <Button size="sm" variant="outline" disabled={busy} onClick={acrescentar}><FilePlus2 /> Acrescentar e ler</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

type Prefill = {
  pessoa: string;
  vinculos: { id: string; rotulo: string; massa: string }[];
  folhas: { id: string; rotulo: string; massa: string }[];
  sugestao: Record<string, string | number | boolean | null>;
};
type Result = { concessao: string; processo: string; beneficio: string; folha: string; pago_ate: string; comprev_averbacoes: number; tce: string; avisos: string[] };

export function ImplantCard({ job, onChanged }: { job: JobLite; onChanged: () => void }) {
  const { can } = useSession();
  const pre = useSWR<Prefill>(!job.concession && job.person ? `leitura/leituras/${job.id}/implantacao` : null, fetcher);
  const [f, setF] = useState<Record<string, string | boolean>>({});
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<Result | null>(null);

  if (job.concession || res) {
    const cid = res?.concessao ?? job.concession;
    return (
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-success" /> Benefício implantado</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-xs">
          {res && <p>Processo <b>{res.processo}</b> · folha <b>{res.folha}</b> · pago pelo sistema anterior até <b>{res.pago_ate}</b> (sem retroativo desse período) · TCE-RJ: <b>{res.tce}</b>
            {res.comprev_averbacoes > 0 && <> · <b>{res.comprev_averbacoes}</b> averbação(ões) para o COMPREV</>}</p>}
          {res?.avisos.map((a, i) => <p key={i} className="text-warning">⚠ {a}</p>)}
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm" variant="outline"><Link href={`/concessao/processo/${cid}`}>Abrir a concessão</Link></Button>
            <Button asChild size="sm" variant="outline"><Link href={`/concessao/processo/${cid}/ficha`}>Ficha FATIMA</Link></Button>
            {job.person && <Button asChild size="sm" variant="outline"><Link href={`/cadastros/pessoas/${job.person}`}>Pasta do Servidor</Link></Button>}
            <Button asChild size="sm" variant="outline"><Link href="/comprev/processos">COMPREV</Link></Button>
          </div>
        </CardContent>
      </Card>
    );
  }
  if (!can("concessao.implantacao", "aprovar")) {
    return <Card><CardContent className="p-4 text-xs text-muted-foreground">A implantação na folha é feita pelo setor de Folha (permissão “Publicação e implantação em folha”).</CardContent></Card>;
  }
  if (!pre.data) return <Card><CardContent className="p-4"><Loader2 className="animate-spin" /></CardContent></Card>;
  const s = pre.data.sugestao;
  const v = (k: string) => (k in f ? f[k] : s[k] ?? "") as string;
  const b = (k: string) => (k in f ? Boolean(f[k]) : Boolean(s[k]));
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value }));
  const T = (k: string, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}, hint?: string) => (
    <FormField label={label} htmlFor={`im-${k}`} hint={hint}><Input id={`im-${k}`} value={v(k)} onChange={set(k)} {...props} /></FormField>
  );

  const implantar = async () => {
    setBusy(true);
    try {
      const body = Object.fromEntries(Object.keys({ ...s, ...f }).map((k) => [k, k in f ? f[k] : s[k]]));
      const r = await api<Result>(`leitura/leituras/${job.id}/implantar`, { method: "POST", body: { ...body, password } });
      setRes(r);
      toast.success(`Aposentadoria implantada na folha ${r.folha} (processo ${r.processo}).`);
      onChanged();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Rocket className="h-4 w-4" /> Implantar benefício já concedido</CardTitle>
        <Badge variant="info">preenchido com o que foi lido — confira</Badge></CardHeader>
      <CardContent className="space-y-4 text-xs">
        <p className="text-muted-foreground">
          Para aposentadoria que o RPPS já concedeu (o processo veio digitalizado). O sistema registra a concessão como concluída
          (sem passar de novo por Jurídico e Presidência), cria o processo no Protocolo com o número original, implanta na folha
          e encerra o vínculo. Fica pronto para a Ficha FATIMA e para o COMPREV.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <FormField label="Benefício" htmlFor="im-tipo">
            <Select id="im-tipo" value="APOSENTADORIA" disabled><option value="APOSENTADORIA">Aposentadoria</option></Select>
          </FormField>
          <FormField label="Modalidade" htmlFor="im-modalidade">
            <Select id="im-modalidade" value={v("modalidade")} onChange={set("modalidade")}>
              <option value="">Selecione…</option>{MODALIDADES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </Select>
          </FormField>
          <FormField label="Vínculo" htmlFor="im-vinculo" className="lg:col-span-2">
            <Select id="im-vinculo" value={v("vinculo")} onChange={set("vinculo")}>
              <option value="">Sem vínculo</option>{pre.data.vinculos.map((l) => <option key={l.id} value={l.id}>{l.rotulo}</option>)}
            </Select>
          </FormField>
          <div className="sm:col-span-2 lg:col-span-4">{T("fundamentacao", "Fundamentação legal")}</div>
          {T("ato_numero", "Nº do ato (portaria)")}
          {T("ato_data", "Data do ato", { type: "date" })}
          {T("publicacao_data", "Data da publicação", { type: "date" })}
          {T("publicacao_veiculo", "Veículo de publicação")}
          {T("inicio", "Início do benefício", { type: "date" }, "Data de vigência (em geral, a publicação).")}
          {T("valor", "Valor atual do benefício (R$)", {}, String(s.valor_origem || "Use o contracheque de inativo mais recente."))}
          <FormField label="Folha" htmlFor="im-folha">
            <Select id="im-folha" value={v("folha")} onChange={set("folha")}>{pre.data.folhas.map((g) => <option key={g.id} value={g.id}>{g.rotulo}</option>)}</Select>
          </FormField>
          {T("pago_ate", "Pago pelo sistema anterior até", { type: "month" }, "A folha do SIST não paga retroativo até este mês.")}
          {T("processo_original", "Nº do processo original")}
          {T("requerimento_data", "Data do requerimento", { type: "date" })}
          <label className="flex items-center gap-2 self-end pb-2"><Checkbox checked={b("integralidade")} onChange={set("integralidade")} /> Integralidade</label>
          <label className="flex items-center gap-2 self-end pb-2"><Checkbox checked={b("paridade")} onChange={set("paridade")} /> Paridade</label>
          <FormField label="TCE-RJ (Deliberação 260)" htmlFor="im-tce">
            <Select id="im-tce" value={v("tce")} onChange={set("tce")}>
              <option value="">Ainda não enviado (fica na lista a enviar)</option><option value="ENVIADO">Enviado, aguardando julgamento</option>
              <option value="LEGAL">Julgado legal (registrado)</option><option value="RESSALVA">Legal com ressalva</option>
            </Select>
          </FormField>
          {v("tce") && <>{T("tce_processo", "Nº do processo no TCE-RJ")}{T("tce_envio", "Enviado em", { type: "date" })}</>}
          {(v("tce") === "LEGAL" || v("tce") === "RESSALVA") && T("tce_julgamento", "Julgado em", { type: "date" })}
        </div>
        <div className="flex flex-wrap items-end gap-3 border-t pt-3">
          <FormField label="Sua senha (assinatura eletrônica)" htmlFor="im-senha">
            <Input id="im-senha" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-64" />
          </FormField>
          <Button onClick={implantar} disabled={busy || !password}>{busy ? <Loader2 className="animate-spin" /> : <Rocket />} Implantar na folha</Button>
        </div>
      </CardContent>
    </Card>
  );
}
