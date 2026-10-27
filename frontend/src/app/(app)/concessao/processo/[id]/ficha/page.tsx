"use client";

import { use } from "react";
import useSWR from "swr";
import { Download, Printer } from "lucide-react";
import Link from "next/link";

import { ErrorState } from "@/components/shared/data-states";
import { RequirePermission } from "@/components/shared/require-permission";
import { Button } from "@/components/ui/button";
import { fetcher } from "@/lib/api";
import { formatCurrency, formatInt } from "@/lib/format";
import type { TimeReport } from "@/lib/types";

type Ficha = {
  tipo: string; pensao: boolean; avisos: string[];
  enquadramento: { nome: string; fundamento: string } | null;
  passos: {
    "1_informacoes_iniciais": { servidor: Record<string, string>; aposentadoria: Record<string, string> };
    "2_tempo_de_contribuicao": TimeReport | null;
    "3_ultima_remuneracao": { competencia: string; parcelas: Record<string, string>[] };
    "4_salario_de_contribuicao": { media: string; competencias: number; observacao: string };
    "5_proventos": { parcelas: Record<string, string>[]; total: string; forma_de_calculo: string };
    "6_acumulacao": { observacao: string };
    "7_documentos": { item: string; documento: string }[];
  };
};

export default function FichaPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequirePermission module="concessao.processos">
      <FichaView id={id} />
    </RequirePermission>
  );
}

function KV({ data }: { data: Record<string, string> }) {
  return (
    <table className="w-full border-collapse">
      <tbody>{Object.entries(data).filter(([, v]) => v).map(([k, v]) => (
        <tr key={k} className="border-b"><td className="w-1/3 py-0.5 pr-3 text-gray-600">{k}</td><td className="py-0.5 font-medium">{v}</td></tr>
      ))}</tbody>
    </table>
  );
}

function Rows({ rows }: { rows: Record<string, string>[] }) {
  if (!rows.length) return <p className="text-gray-500">—</p>;
  const cols = Object.keys(rows[0]);
  return (
    <table className="w-full border-collapse">
      <thead><tr className="border-b border-black text-left">{cols.map((c) => <th key={c} className="pr-2">{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className="border-b">{cols.map((c) => <td key={c} className="pr-2">{c === "Valor" && r[c] ? formatCurrency(r[c]) : r[c]}</td>)}</tr>)}</tbody>
    </table>
  );
}

function FichaView({ id }: { id: string }) {
  const { data, error } = useSWR<Ficha>(`concessoes/${id}/ficha`, fetcher);
  if (error) return <ErrorState error={error} />;
  if (!data) return <div className="h-64 animate-pulse rounded-lg bg-muted" />;
  const p = data.passos;
  const t = p["2_tempo_de_contribuicao"];

  return (
    <>
      <div className="mb-3 flex items-center justify-between print:hidden">
        <Link href={`/concessao/processo/${id}`} className="text-xs text-primary hover:underline">← Voltar ao processo</Link>
        <div className="flex gap-2">
          <Link href={`/previdenciaria/historico-contributivo`}><Button variant="outline" size="sm"><Download /> SalContr.txt (Histórico Contributivo)</Button></Link>
          <Button size="sm" onClick={() => window.print()}><Printer /> Imprimir</Button>
        </div>
      </div>
      <article className="mx-auto max-w-[900px] space-y-4 rounded-md border bg-white p-8 text-[12px] text-black print:max-w-none print:border-0 print:p-0">
        <header className="border-b-2 border-black pb-2">
          <div className="text-base font-bold">FICHA PARA O eTCERJ — MÓDULO DELIBERAÇÃO 260 (FATIMA)</div>
          <div>{data.tipo} · transcrever nos Passos do sistema do TCE-RJ</div>
          {data.avisos.length > 0 && <ul className="mt-1 text-[11px] text-amber-700">{data.avisos.map((a) => <li key={a}>⚠ {a}</li>)}</ul>}
        </header>
        <section><h3 className="mb-1 font-bold">PASSO 1 — Informações iniciais · Servidor</h3><KV data={p["1_informacoes_iniciais"].servidor} /></section>
        <section><h3 className="mb-1 font-bold">PASSO 1 — Dados da aposentadoria</h3><KV data={p["1_informacoes_iniciais"].aposentadoria} /></section>
        <section>
          <h3 className="mb-1 font-bold">PASSO 2 — Tempo de contribuição (sem períodos concomitantes)</h3>
          {t && (
            <table className="w-full border-collapse">
              <thead><tr className="border-b border-black text-left"><th>Natureza</th><th>Início</th><th>Fim</th><th>Origem</th><th className="text-right">Dias líquidos</th></tr></thead>
              <tbody>{t.periodos.map((x, i) => (
                <tr key={i} className="border-b"><td>{x.natureza} — {x.natureza_display}</td><td>{x.inicio}</td><td>{x.fim_apurado}</td><td>{x.descricao}</td><td className="text-right">{formatInt(x.dias_liquidos + x.acrescimo_conversao)}</td></tr>
              ))}</tbody>
              <tfoot><tr className="font-bold"><td colSpan={4}>Total de contribuição</td><td className="text-right">{t.totais.contribuicao.texto}</td></tr></tfoot>
            </table>
          )}
        </section>
        <section><h3 className="mb-1 font-bold">PASSO 3 — Última remuneração {p["3_ultima_remuneracao"].competencia && `(${p["3_ultima_remuneracao"].competencia})`}</h3><Rows rows={p["3_ultima_remuneracao"].parcelas} /></section>
        <section>
          <h3 className="mb-1 font-bold">PASSO 4 — Salário de contribuição</h3>
          <p>Média: {p["4_salario_de_contribuicao"].media ? formatCurrency(p["4_salario_de_contribuicao"].media) : "—"} · {p["4_salario_de_contribuicao"].competencias} competências. {p["4_salario_de_contribuicao"].observacao}</p>
        </section>
        <section>
          <h3 className="mb-1 font-bold">PASSO 5 — Proventos</h3>
          <Rows rows={p["5_proventos"].parcelas} />
          <p className="mt-1"><b>Total:</b> {p["5_proventos"].total ? formatCurrency(p["5_proventos"].total) : "—"} — {p["5_proventos"].forma_de_calculo}</p>
        </section>
        <section><h3 className="mb-1 font-bold">PASSO 6 — Acumulação</h3><p>{p["6_acumulacao"].observacao}</p></section>
        <section>
          <h3 className="mb-1 font-bold">PASSO 7 — Documentos digitalizados (assinados digitalmente)</h3>
          <ul className="list-disc pl-5">{p["7_documentos"].map((d) => <li key={d.item}><b>{d.item}</b> — {d.documento}</li>)}</ul>
        </section>
        {data.enquadramento && (
          <section><h3 className="mb-1 font-bold">PASSO 8 — Análise</h3><p>Requisitos da regra <b>{data.enquadramento.nome}</b> ({data.enquadramento.fundamento}) conferidos pelo SIST FOPAG na data de validade.</p></section>
        )}
      </article>
    </>
  );
}
