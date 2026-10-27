"use client";

import { useState } from "react";
import useSWR from "swr";
import { AlertTriangle, CheckCircle2, Clock, Printer, XCircle } from "lucide-react";

import { ErrorState } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetcher } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { RuleSimulation, Simulation } from "@/lib/types";

const GROUPS: [RuleSimulation["grupo"], string][] = [
  ["PERMANENTE", "Regra permanente (EC 103 — Emenda à LOM 28/2025)"],
  ["TRANSICAO", "Regras de transição (ingresso antes da reforma local)"],
  ["DIREITO_ADQUIRIDO", "Direito adquirido (requisitos cumpridos antes da reforma local)"],
  ["COMPULSORIA", "Compulsória"],
];

const STATUS = {
  CUMPRIDA: { label: "Requisitos cumpridos", icon: CheckCircle2, cls: "border-success-border bg-success-soft text-success" },
  CUMPRIRA: { label: "Cumprirá", icon: Clock, cls: "border-info-border bg-info-soft text-info" },
  NAO_ALCANCAVEL: { label: "Não alcançável", icon: XCircle, cls: "border-border bg-muted text-muted-foreground" },
  NAO_SE_APLICA: { label: "Não se aplica", icon: XCircle, cls: "border-border bg-muted text-muted-foreground" },
};

export function SimulacaoPanel({ personId }: { personId: string }) {
  const [on, setOn] = useState("");
  const [showAll, setShowAll] = useState(false);
  const { data, error, isLoading } = useSWR<Simulation>(`previdencia/simulacao/${personId}${on ? `?data=${on}` : ""}`, fetcher);

  if (error) return <ErrorState error={error} />;
  if (isLoading || !data) return <div className="h-48 animate-pulse rounded-md bg-muted" />;

  const best = data.regras.find((r) => r.situacao === "CUMPRIDA" || r.situacao === "CUMPRIRA");
  const visible = data.regras.filter((r) => showAll || r.situacao !== "NAO_SE_APLICA");

  return (
    <div className="space-y-4 print:text-[11px]">
      <div className="flex flex-wrap items-end justify-between gap-3 print:hidden">
        <FormField label="Simular na data" htmlFor="sim-on" hint="Vazio = hoje.">
          <Input id="sim-on" type="date" value={on} onChange={(e) => setOn(e.target.value)} className="w-44" />
        </FormField>
        <div className="flex gap-2">
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Mostrar regras que não se aplicam</label>
          <Button size="sm" variant="outline" onClick={() => window.print()}><Printer /> Imprimir</Button>
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Fact label="Idade" value={`${data.idade} anos`} />
        <Fact label="Tempo de contribuição" value={String(data.tempo.contribuicao_texto)} />
        <Fact label="Serviço público" value={String(data.tempo.servico_publico_texto)} hint={`Ingresso: ${formatDate(data.ingresso_servico_publico)}`} />
        <Fact label="Cargo / carreira" value={String(data.tempo.cargo_texto)} hint={`Carreira: ${data.tempo.carreira_texto}`} />
        {data.professor && <Fact label="Magistério" value={String(data.tempo.magisterio_texto)} />}
        <Fact label="Média (100%)" value={data.medias.media100 ? formatCurrency(data.medias.media100) : "—"} hint={`${data.medias.meses} competência(s)`} />
        <Fact label="Média (80% maiores)" value={data.medias.media80 ? formatCurrency(data.medias.media80) : "—"} />
        <Fact label="Última remuneração RPPS" value={data.medias.ultima_remuneracao_rpps ? formatCurrency(data.medias.ultima_remuneracao_rpps) : "—"} />
      </div>

      <div className={cn("rounded-md border px-3 py-2 text-xs", data.abono_permanencia.ja_tem_direito ? "border-success-border bg-success-soft text-success" : "bg-muted/40")}>
        <strong>Abono de permanência (Emenda à LOM 28/2025, art. 6º): </strong>
        {data.abono_permanencia.data
          ? data.abono_permanencia.ja_tem_direito
            ? `tem direito desde ${formatDate(data.abono_permanencia.data)}, se optar por permanecer em atividade.`
            : `terá direito a partir de ${formatDate(data.abono_permanencia.data)}.`
          : "não alcançável pelas regras voluntárias com os dados atuais."}
        {best && <> Primeira regra disponível: <strong>{best.nome}</strong> em {formatDate(best.data_elegibilidade)}.</>}
      </div>

      {data.avisos.length > 0 && (
        <div className="flex gap-2 rounded-md border border-warning-border bg-warning-soft px-3 py-2 text-xs text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><ul>{data.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      )}

      {GROUPS.map(([g, title]) => {
        const rules = visible.filter((r) => r.grupo === g);
        if (!rules.length) return null;
        return (
          <div key={g}>
            <div className="section-label mb-2">{title}</div>
            <div className="grid gap-3 xl:grid-cols-2">{rules.map((r) => <RuleCard key={r.codigo} r={r} />)}</div>
          </div>
        );
      })}
      <p className="text-2xs text-muted-foreground">
        Simulação com base nos dados do Cadastro Único, averbações e histórico contributivo. Não substitui a análise do processo de concessão.
        Aposentadoria da pessoa com deficiência (EC 103, art. 22 — LC 142/2013) depende de avaliação biopsicossocial e não é simulada.
      </p>
    </div>
  );
}

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="section-label">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
      {hint && <div className="text-2xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

function RuleCard({ r }: { r: RuleSimulation }) {
  const st = STATUS[r.situacao];
  const Icon = st.icon;
  return (
    <div className="rounded-md border bg-card break-inside-avoid">
      <div className="flex items-start justify-between gap-2 border-b px-3 py-2">
        <div>
          <div className="text-xs font-semibold">{r.nome} {r.professor && <Badge className="ml-1">Professor</Badge>}</div>
          <div className="text-2xs text-muted-foreground">{r.fundamento}</div>
        </div>
        <span className={cn("inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-2xs font-semibold", st.cls)}>
          <Icon className="h-3 w-3" /> {st.label}{r.data_elegibilidade ? ` ${r.situacao === "CUMPRIDA" ? "desde" : "em"} ${formatDate(r.data_elegibilidade)}` : ""}
        </span>
      </div>
      {r.requisitos.length > 0 && (
        <table className="w-full text-2xs">
          <thead><tr className="text-muted-foreground"><th className="px-3 py-1 text-left font-medium">Requisito</th><th className="px-2 py-1 text-left font-medium">Exigido</th><th className="px-2 py-1 text-left font-medium">{r.data_referencia ? `Em ${formatDate(r.data_referencia)}` : "Atual"}</th><th /></tr></thead>
          <tbody>
            {r.requisitos.map((q) => (
              <tr key={q.chave} className="border-t">
                <td className="px-3 py-1">{q.descricao}</td>
                <td className="px-2 py-1">{q.exigido}</td>
                <td className="px-2 py-1">{q.atual}</td>
                <td className="px-2 py-1">{q.cumprido ? <CheckCircle2 className="h-3.5 w-3.5 text-success" /> : <XCircle className="h-3.5 w-3.5 text-muted-foreground" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="space-y-1 border-t px-3 py-2 text-2xs">
        <div><span className="text-muted-foreground">Proventos: </span>{r.proventos}</div>
        <div><span className="text-muted-foreground">Paridade: </span>{r.paridade || "—"}</div>
        {r.estimativa?.valor && (
          <div className="font-semibold">Estimativa: {formatCurrency(r.estimativa.valor)} <span className="font-normal text-muted-foreground">({r.estimativa.forma})</span></div>
        )}
        {r.estimativa?.avisos.map((a) => <div key={a} className="text-warning">{a}</div>)}
        {r.observacoes.map((o) => <div key={o} className="text-muted-foreground">{o}</div>)}
      </div>
    </div>
  );
}
