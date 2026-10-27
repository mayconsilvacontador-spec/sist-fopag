"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, History, Loader2, Percent, Plus, Upload } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/shared/form-field";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, download, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { EmploymentLink } from "@/lib/types";

const BASE = "ativos/ficha-financeira";
const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez", "13º"];
const CATEGORIAS = [
  { value: "", label: "Outras" },
  { value: "CONTRIB_RPPS", label: "Contribuição do servidor ao RPPS" },
  { value: "BASE_RPPS", label: "Base de contribuição RPPS" },
  { value: "PATRONAL", label: "Patronal (informativa)" },
  { value: "IRRF", label: "IRRF" },
];

type Rubrica = { codigo: string; rubrica: string; natureza: string; classificacao: string; total?: string };
type Resultado = {
  linhas: number; incluidas: number; atualizadas: number; total_erros: number; servidores: number; gravado: boolean;
  periodo: [string, string] | null; erros: { linha: number; mensagem: string }[]; rubricas: Rubrica[];
  sem_classificacao_rpps: boolean;
};
type Ficha = {
  ano: number; matriculas: string[]; fontes: string[]; anos: number[];
  linhas: { codigo: string; rubrica: string; natureza: string; classificacao: string; valores: Record<string, string>; total: string }[];
  totais: Record<string, Record<string, string>>;
};
type Contrib = {
  competencias: {
    competencia: string; folha: string; matricula: string; orgao: string; fonte: string; base: string; base_estimada: boolean;
    descontado: string; aliquota_aplicada: string | null; aliquota_legal: string | null; devido: string | null;
    diferenca: string | null; patronal: string | null; avisos: string[];
    repasse_orgao: { situacao: string; devido: string | null; pago: string | null };
  }[];
  totais: Record<string, string>; com_aviso: number; anos: number[];
};

const money = (v?: string | null) => (v ? formatCurrency(v) : "");

/** Importação da ficha financeira (validar → conferir → gravar). Com `personId`, só aceita linhas desse servidor. */
export function FichaImport({ personId, onDone }: { personId?: string; onDone?: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<Resultado | null>(null);

  const send = async (confirmar: boolean) => {
    const file = ref.current?.files?.[0];
    if (!file) { toast.error("Selecione o arquivo da ficha financeira."); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (personId) fd.append("pessoa", personId);
      if (confirmar) fd.append("confirmar", "1");
      const r = await fetch(`/api/backend/${BASE}/importar`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || "Falha na importação.");
      setRes(body);
      if (confirmar) {
        toast.success(`Ficha importada: ${body.incluidas} linha(s) nova(s), ${body.atualizadas} atualizada(s).`);
        if (ref.current) ref.current.value = "";
        onDone?.();
      }
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <FileSpreadsheet className="h-5 w-5 text-primary" />
        <span className="font-semibold">Importar ficha financeira</span>
        <span className="text-xs text-muted-foreground">(do sistema anterior; uma linha por rubrica de cada mês)</span>
        <div className="flex-1" />
        <Button variant="outline" size="sm"
          onClick={() => download(`${BASE}/modelo`, "SIST_tabela_padrao_ficha_financeira.xlsx").catch((e) => toast.error((e as Error).message))}>
          <Download /> Tabela padrão
        </Button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input ref={ref} type="file" accept=".csv,.txt,.xlsx" className="text-xs" onChange={() => setRes(null)} />
        <Button size="sm" variant="outline" onClick={() => send(false)} disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Conferir arquivo
        </Button>
        {res && !res.gravado && res.incluidas + res.atualizadas > 0 && (
          <Button size="sm" onClick={() => send(true)} disabled={busy}><Upload /> Gravar {res.incluidas + res.atualizadas} linha(s)</Button>
        )}
      </div>
      {res && (
        <div className="mt-3 space-y-2 text-xs">
          <div className="flex flex-wrap gap-2">
            <Badge variant={res.gravado ? "success" : "info"}>{res.gravado ? "Gravado" : "Conferência (nada gravado ainda)"}</Badge>
            <span>{res.linhas} linha(s) · {res.incluidas} nova(s) · {res.atualizadas} atualizada(s) · {res.servidores} servidor(es)
              {res.periodo && ` · ${res.periodo[0]} a ${res.periodo[1]}`}</span>
            {res.total_erros > 0 && <Badge variant="critical">{res.total_erros} com erro (serão ignoradas)</Badge>}
          </div>
          {res.sem_classificacao_rpps && (
            <p className="flex items-center gap-1 text-warning"><AlertTriangle className="h-3.5 w-3.5" />
              Nenhuma rubrica foi reconhecida como contribuição ao RPPS. Classifique abaixo, depois de gravar, para o controle funcionar.</p>
          )}
          {res.erros.length > 0 && (
            <ul className="max-h-32 overflow-y-auto rounded border bg-card p-2 thin-scroll">
              {res.erros.map((e, i) => <li key={i}>Linha {e.linha}: {e.mensagem}</li>)}
            </ul>
          )}
          {!res.gravado && res.rubricas.length > 0 && (
            <p className="text-muted-foreground">
              Rubricas do arquivo: {res.rubricas.map((r) => `${r.codigo} ${r.rubrica}${r.classificacao ? ` → ${CATEGORIAS.find((c) => c.value === r.classificacao)?.label}` : ""}`).join("; ")}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Classificação das rubricas importadas (qual é o desconto previdenciário, a base, a patronal e o IRRF). */
export function RubricClassification({ personId }: { personId?: string }) {
  const { can } = useSession();
  const { data, isLoading, mutate } = useSWR<Rubrica[]>(`${BASE}/rubricas${qs({ pessoa: personId })}`, fetcher);
  const change = async (codigo: string, classificacao: string) => {
    try {
      const r = await api<{ linhas: number }>(`${BASE}/classificar`, { method: "POST", body: { codigo, classificacao, pessoa: personId } });
      toast.success(`Rubrica ${codigo} reclassificada (${r.linhas} linha(s)).`);
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };
  return (
    <Table>
      <TableHeader><TableRow><TableHead>Código</TableHead><TableHead>Rubrica</TableHead><TableHead>Natureza</TableHead>
        <TableHead className="text-right">Total importado</TableHead><TableHead>Classificação</TableHead></TableRow></TableHeader>
      <TableBody>
        {isLoading && <LoadingRows cols={5} rows={2} />}
        {data?.map((r) => (
          <TableRow key={r.codigo}>
            <TableCell className="font-mono text-xs">{r.codigo}</TableCell>
            <TableCell>{r.rubrica}</TableCell>
            <TableCell className="text-xs">{r.natureza === "PROVENTO" ? "Provento" : r.natureza === "DESCONTO" ? "Desconto" : "Base"}</TableCell>
            <TableCell className="text-right">{money(r.total)}</TableCell>
            <TableCell>
              <Select value={r.classificacao} disabled={!can("ativos.ficha_financeira", "incluir")}
                onChange={(e) => change(r.codigo, e.target.value)} className="h-8 w-64 text-xs" aria-label={`Classificação ${r.codigo}`}>
                {CATEGORIAS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </Select>
            </TableCell>
          </TableRow>
        ))}
        {data?.length === 0 && <EmptyRow cols={5} text="Nenhuma ficha financeira importada." />}
      </TableBody>
    </Table>
  );
}

/** Ficha financeira anual (rubrica × mês), com Excel. */
export function FichaFinanceira({ personId }: { personId: string }) {
  const { can } = useSession();
  const [ano, setAno] = useState<number | null>(null);
  const [mat, setMat] = useState("");
  const { data, isLoading, mutate } = useSWR<Ficha>(`${BASE}/${personId}${qs({ ano: ano ?? undefined, matricula: mat })}`, fetcher, {
    onSuccess: (d) => { if (ano === null && d.anos.length && !d.anos.includes(d.ano)) setAno(d.anos[0]); },
  });
  const [showImport, setShowImport] = useState(false);
  const year = ano ?? data?.ano;
  const years = Array.from(new Set([...(data?.anos ?? []), ...(year ? [year] : [])])).sort((a, b) => b - a);
  const tot = data?.totais ?? {};

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Select value={String(year ?? "")} onChange={(e) => setAno(Number(e.target.value))} className="h-8 w-28" aria-label="Ano">
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </Select>
        {(data?.matriculas.length ?? 0) > 1 && (
          <Select value={mat} onChange={(e) => setMat(e.target.value)} className="h-8 w-44" aria-label="Matrícula">
            <option value="">Todas as matrículas</option>
            {data!.matriculas.map((m) => <option key={m} value={m}>Matrícula {m}</option>)}
          </Select>
        )}
        {data?.fontes.map((f) => <Badge key={f} variant="neutral">{f === "FOLHA" ? "Folha de Ativos do SIST" : "Ficha importada"}</Badge>)}
        <div className="flex-1" />
        {can("ativos.ficha_financeira", "exportar") && year && (
          <Button variant="outline" size="sm"
            onClick={() => download(`${BASE}/${personId}/excel${qs({ ano: year, matricula: mat })}`, `ficha_financeira_${year}.xlsx`).catch((e) => toast.error((e as Error).message))}>
            <Download /> Gerar ficha (Excel)
          </Button>
        )}
        <Button variant="outline" size="sm"
          onClick={() => download(`${BASE}/modelo`, "SIST_tabela_padrao_ficha_financeira.xlsx").catch((e) => toast.error((e as Error).message))}>
          <FileSpreadsheet /> Modelo de importação
        </Button>
        {can("ativos.ficha_financeira", "incluir") && (
          <Button variant="outline" size="sm" onClick={() => setShowImport((s) => !s)}><Upload /> Importar ficha financeira</Button>
        )}
      </div>
      {showImport && <div className="mb-3"><FichaImport personId={personId} onDone={() => mutate()} /></div>}
      <div className="overflow-x-auto rounded-lg border thin-scroll">
        <table className="w-full min-w-[1100px] text-xs tabular">
          <thead className="bg-muted/60">
            <tr>
              <th className="sticky left-0 bg-muted px-2 py-2 text-left font-semibold">Rubrica</th>
              {MESES.map((m) => <th key={m} className="px-2 py-2 text-right font-semibold">{m}</th>)}
              <th className="px-2 py-2 text-right font-semibold">Total</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={15} className="p-4 text-center text-muted-foreground">Carregando…</td></tr>}
            {data?.linhas.map((ln, i) => {
              const first = i === 0 || data.linhas[i - 1].natureza !== ln.natureza;
              return (
                <Fragment key={`${ln.natureza}-${ln.codigo}`}>
                  {first && (
                    <tr className="bg-muted/30"><td colSpan={15} className="px-2 py-1 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {ln.natureza === "PROVENTO" ? "Proventos" : ln.natureza === "DESCONTO" ? "Descontos" : "Bases e informativos"}
                    </td></tr>
                  )}
                  <tr className="border-t">
                    <td className="sticky left-0 max-w-[260px] truncate bg-card px-2 py-1" title={ln.rubrica}>
                      <span className="font-mono text-muted-foreground">{ln.codigo}</span> {ln.rubrica}
                      {ln.classificacao === "CONTRIB_RPPS" && <Badge variant="default" className="ml-1">RPPS</Badge>}
                    </td>
                    {MESES.map((_, m) => <td key={m} className="px-2 py-1 text-right">{money(ln.valores[String(m + 1)])}</td>)}
                    <td className="px-2 py-1 text-right font-semibold">{money(ln.total)}</td>
                  </tr>
                </Fragment>
              );
            })}
            {data && data.linhas.length === 0 && (
              <tr><td colSpan={15} className="p-6 text-center text-muted-foreground">
                Sem valores em {data.ano}. Importe a ficha financeira do sistema anterior ou calcule a Folha de Ativos.
              </td></tr>
            )}
            {data && data.linhas.length > 0 && ([
              ["proventos", "Total de proventos"], ["descontos", "Total de descontos"], ["liquido", "Líquido"],
              ["CONTRIB_RPPS", "Contribuição do servidor ao RPPS"],
            ] as const).map(([k, label]) => (
              <tr key={k} className="border-t bg-muted/40 font-semibold">
                <td className="sticky left-0 bg-muted px-2 py-1">{label}</td>
                {MESES.map((_, m) => <td key={m} className="px-2 py-1 text-right">{money(tot[k]?.[String(m + 1)])}</td>)}
                <td className="px-2 py-1 text-right">{money(tot[k]?.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Controle da contribuição do servidor: descontado × devido × repasse do órgão. */
export function ContribuicoesPanel({ personId }: { personId: string }) {
  const { can } = useSession();
  const [ano, setAno] = useState("");
  const { data, isLoading, mutate } = useSWR<Contrib>(`${BASE}/${personId}/contribuicoes${qs({ ano })}`, fetcher);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const t = data?.totais;

  const toHistory = async () => {
    setBusy(true);
    try {
      const r = await api<{ incluidos: number; ja_existiam: number }>(`${BASE}/${personId}/historico`, { method: "POST" });
      toast.success(`${r.incluidos} competência(s) incluída(s) no histórico contributivo; ${r.ja_existiam} já existiam e foram mantidas.`);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {([["base", "Base de contribuição"], ["descontado", "Descontado do servidor"], ["devido", "Devido pela alíquota"],
          ["diferenca", "Diferença"], ["patronal", "Patronal (estimada)"]] as const).map(([k, l]) => (
          <div key={k} className="rounded-lg border bg-card px-3 py-2">
            <div className="text-2xs uppercase tracking-wide text-muted-foreground">{l}</div>
            <div className={`text-base font-bold ${k === "diferenca" && t && Number(t[k]) < 0 ? "text-critical" : "text-primary-strong"}`}>{t ? formatCurrency(t[k]) : "…"}</div>
          </div>
        ))}
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Select value={ano} onChange={(e) => setAno(e.target.value)} className="h-8 w-36" aria-label="Ano">
          <option value="">Todos os anos</option>
          {data?.anos.map((y) => <option key={y} value={y}>{y}</option>)}
        </Select>
        {!!data?.com_aviso && <Badge variant="warning">{data.com_aviso} competência(s) com aviso</Badge>}
        <div className="flex-1" />
        {can("arrecadacao.aliquotas") && (
          <Button asChild variant="outline" size="sm"><Link href="/arrecadacao/aliquotas"><Percent /> Alíquotas</Link></Button>
        )}
        {can("ativos.ficha_financeira", "incluir") && (
          <Button variant="outline" size="sm" onClick={() => setAdding((a) => !a)}><Plus /> Lançar competência</Button>
        )}
        {can("previdenciaria.historico_contributivo", "incluir") && can("ativos.ficha_financeira", "incluir") && (
          <Button variant="outline" size="sm" onClick={toHistory} disabled={busy || !data?.competencias.length}>
            {busy ? <Loader2 className="animate-spin" /> : <History />} Levar bases ao histórico contributivo
          </Button>
        )}
      </div>
      {adding && <LancarCompetencia personId={personId} onDone={() => { setAdding(false); mutate(); }} />}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Competência</TableHead><TableHead className="text-right">Base</TableHead>
            <TableHead className="text-right">Descontado</TableHead><TableHead className="text-right">Alíquota</TableHead>
            <TableHead className="text-right">Devido</TableHead><TableHead className="text-right">Diferença</TableHead>
            <TableHead className="text-right">Patronal</TableHead><TableHead>Repasse do órgão ao RPPS</TableHead><TableHead>Avisos</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={9} rows={3} />}
          {data?.competencias.map((c, i) => (
            <TableRow key={i} className={c.avisos.length ? "bg-warning-soft/40" : ""}>
              <TableCell>
                <span className="font-medium">{c.competencia}</span>{c.folha !== "MENSAL" && <Badge variant="neutral" className="ml-1">{c.folha === "DECIMO" ? "13º" : c.folha}</Badge>}
                <div className="text-2xs text-muted-foreground">mat. {c.matricula || "—"} · {c.fonte === "FOLHA" ? "Folha do SIST" : "importada"}</div>
              </TableCell>
              <TableCell className="text-right">{money(c.base)}{c.base_estimada && <div className="text-2xs text-muted-foreground">estimada</div>}</TableCell>
              <TableCell className="text-right font-semibold">{money(c.descontado)}</TableCell>
              <TableCell className="text-right text-xs">{c.aliquota_aplicada ? `${c.aliquota_aplicada}%` : "—"}
                {c.aliquota_legal && <div className="text-2xs text-muted-foreground">legal {c.aliquota_legal}%</div>}</TableCell>
              <TableCell className="text-right">{money(c.devido)}</TableCell>
              <TableCell className={`text-right ${c.diferenca && Math.abs(Number(c.diferenca)) > 0.05 ? "font-semibold text-critical" : ""}`}>{money(c.diferenca)}</TableCell>
              <TableCell className="text-right">{money(c.patronal)}</TableCell>
              <TableCell className="text-xs">
                <Badge variant={c.repasse_orgao.situacao === "Quitado" ? "success" : c.repasse_orgao.situacao === "Sem guia lançada" ? "neutral" : "warning"}>
                  {c.repasse_orgao.situacao}
                </Badge>
                {c.repasse_orgao.devido && <div className="text-2xs text-muted-foreground">guia {money(c.repasse_orgao.devido)} · pago {money(c.repasse_orgao.pago)}</div>}
              </TableCell>
              <TableCell className="text-xs text-warning">{c.avisos.join("; ")}</TableCell>
            </TableRow>
          ))}
          {data?.competencias.length === 0 && (
            <EmptyRow cols={9} text="Sem contribuições: importe a ficha financeira (com a rubrica de desconto previdenciário) ou calcule a Folha de Ativos." />
          )}
        </TableBody>
      </Table>
      <p className="mt-2 text-2xs text-muted-foreground">
        Devido = base × alíquota do servidor vigente na competência (Parâmetros). O repasse mostra a guia de contribuição
        dos servidores do órgão naquela competência (Arrecadação) e quanto já foi pago — o órgão repassa em guia única.
      </p>
    </div>
  );
}

/** Lança uma competência no controle (sem arquivo): base, alíquota e valor descontado. */
function LancarCompetencia({ personId, onDone }: { personId: string; onDone: () => void }) {
  const { can } = useSession();
  const links = useSWR<Paginated<EmploymentLink>>(`employment-links?person=${personId}&page_size=50`, fetcher);
  const [f, setF] = useState({ comp: "", vinculo: "", base: "", aliquota: "", descontado: "", tipo: "MENSAL", historico: true });
  const [vigente, setVigente] = useState<string | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value }));

  useEffect(() => {
    if (!f.comp) { setVigente(undefined); return; }
    const [y, m] = f.comp.split("-");
    api<{ servidor: string | null }>(`arrecadacao/aliquotas?competencia=${m}/${y}`)
      .then((r) => { setVigente(r.servidor); setF((x) => ({ ...x, aliquota: r.servidor ?? x.aliquota })); })
      .catch(() => setVigente(null));
  }, [f.comp]);

  const num = (v: string) => Number(v.includes(",") ? v.replace(/\./g, "").replace(",", ".") : v) || 0;
  const previsto = f.base && f.aliquota ? (num(f.base) * num(f.aliquota)) / 100 : null;

  const save = async () => {
    if (!f.comp || !f.base) { toast.error("Informe a competência e a base."); return; }
    setBusy(true);
    try {
      const [y, m] = f.comp.split("-");
      const r = await api<{ descontado: string; historico: boolean }>(`${BASE}/${personId}/lancar`, {
        method: "POST",
        body: { competencia: `${m}/${y}`, vinculo: f.vinculo || undefined, base: f.base, aliquota: f.aliquota || undefined,
          descontado: f.descontado || undefined, tipo_folha: f.tipo, historico: f.historico },
      });
      toast.success(`Competência ${m}/${y} lançada: descontado ${formatCurrency(r.descontado)}${r.historico ? "; base incluída no histórico contributivo" : ""}.`);
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-3 rounded-lg border bg-muted/30 p-3">
      <div className="mb-2 font-semibold">Lançar competência</div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <FormField label="Competência" htmlFor="lc-comp"><Input id="lc-comp" type="month" value={f.comp} onChange={set("comp")} /></FormField>
        <FormField label="Vínculo" htmlFor="lc-vinc">
          <Select id="lc-vinc" value={f.vinculo} onChange={set("vinculo")}>
            <option value="">—</option>
            {links.data?.results.map((l) => <option key={l.id} value={l.id}>{l.registration} · {l.position_name}</option>)}
          </Select>
        </FormField>
        <FormField label="Tipo de folha" htmlFor="lc-tipo">
          <Select id="lc-tipo" value={f.tipo} onChange={set("tipo")}>
            <option value="MENSAL">Mensal</option><option value="DECIMO">13º salário</option><option value="FERIAS">Férias</option>
            <option value="RESCISAO">Rescisão</option><option value="COMPLEMENTAR">Complementar</option>
          </Select>
        </FormField>
        <FormField label="Base de contribuição (R$)" htmlFor="lc-base"><Input id="lc-base" value={f.base} onChange={set("base")} placeholder="0,00" /></FormField>
        <FormField label="Alíquota do servidor (%)" htmlFor="lc-aliq"
          hint={vigente === undefined ? "Escolha a competência" : vigente ? `Vigente na competência: ${vigente}%` : "Sem alíquota cadastrada para o mês — informe aqui"}>
          <Input id="lc-aliq" value={f.aliquota} onChange={set("aliquota")} placeholder="ex.: 14" />
        </FormField>
        <FormField label="Valor descontado do servidor (R$)" htmlFor="lc-desc"
          hint={previsto !== null ? `Em branco = ${formatCurrency(previsto.toFixed(2))} (base × alíquota)` : "Em branco = base × alíquota"}>
          <Input id="lc-desc" value={f.descontado} onChange={set("descontado")} placeholder="o que saiu no contracheque" />
        </FormField>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" checked={f.historico} onChange={set("historico")} disabled={!can("previdenciaria.historico_contributivo", "incluir")} />
          Incluir a base no histórico contributivo
        </label>
        <div className="flex items-end justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onDone}>Cancelar</Button>
          <Button size="sm" onClick={save} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Plus />} Lançar</Button>
        </div>
      </div>
    </div>
  );
}
