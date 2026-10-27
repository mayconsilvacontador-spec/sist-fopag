"use client";

import { use, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Ban, Printer } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { ErrorState } from "@/components/shared/data-states";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";
import { formatCurrency, formatDate, formatDateTime, formatInt } from "@/lib/format";
import type { CtcRow } from "@/lib/types";

export default function CtcDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequirePermission module="previdenciaria.ctc">
      <CtcDetail id={id} />
    </RequirePermission>
  );
}

function CtcDetail({ id }: { id: string }) {
  const { can } = useSession();
  const { data: c, error, mutate } = useSWR<CtcRow>(`previdencia/ctc/${id}`, fetcher);
  const [cancelling, setCancelling] = useState(false);
  if (error) return <ErrorState error={error} />;
  if (!c) return <div className="h-64 animate-pulse rounded-lg bg-muted" />;
  const s = c.snapshot;

  return (
    <>
      <div className="mb-3 flex items-center justify-between print:hidden">
        <div className="text-sm font-semibold">CTC {c.code} {c.status === "CANCELADA" && <Badge variant="critical">Cancelada</Badge>}</div>
        <div className="flex gap-2">
          {c.status === "EMITIDA" && can("previdenciaria.ctc", "excluir") && (
            <Button variant="outline" size="sm" onClick={() => setCancelling(true)}><Ban /> Cancelar CTC</Button>
          )}
          <Button size="sm" onClick={() => window.print()}><Printer /> Imprimir</Button>
        </div>
      </div>

      <article className="mx-auto max-w-[820px] space-y-4 rounded-md border bg-white p-8 text-[12px] text-black print:max-w-none print:border-0 print:p-0">
        <header className="border-b-2 border-black pb-2 text-center">
          <div className="text-sm font-bold uppercase">{s.instituicao.nome}</div>
          <div>{s.instituicao.ente}{s.instituicao.cnpj ? ` · CNPJ ${s.instituicao.cnpj}` : ""}</div>
          <div className="mt-2 text-base font-bold">CERTIDÃO DE TEMPO DE CONTRIBUIÇÃO Nº {c.code}</div>
          {c.status === "CANCELADA" && <div className="mt-1 font-bold text-red-700">CANCELADA — {c.cancel_reason}</div>}
        </header>

        <section>
          <h3 className="mb-1 font-bold uppercase">1. Dados do segurado</h3>
          <div className="grid grid-cols-2 gap-x-6 gap-y-0.5">
            <div><b>Nome:</b> {s.segurado.nome}</div><div><b>CPF:</b> {s.segurado.cpf}</div>
            <div><b>PIS/PASEP:</b> {s.segurado.pis_pasep || "—"}</div><div><b>RG:</b> {s.segurado.rg || "—"}</div>
            <div><b>Nascimento:</b> {formatDate(s.segurado.nascimento)}</div><div><b>Sexo:</b> {s.segurado.sexo}</div>
            <div><b>Mãe:</b> {s.segurado.mae || "—"}</div><div><b>Pai:</b> {s.segurado.pai || "—"}</div>
          </div>
        </section>

        <section>
          <h3 className="mb-1 font-bold uppercase">2. Vínculos com o ente</h3>
          <table className="w-full border-collapse">
            <thead><tr className="border-b border-black text-left"><th>Matrícula</th><th>Órgão</th><th>Cargo</th><th>Admissão</th><th>Desligamento</th></tr></thead>
            <tbody>{s.vinculos.map((v) => (
              <tr key={v.matricula} className="border-b"><td>{v.matricula}</td><td>{v.orgao}</td><td>{v.cargo}</td><td>{formatDate(v.admissao)}</td><td>{formatDate(v.exoneracao)} {v.motivo && `(${v.motivo})`}</td></tr>
            ))}</tbody>
          </table>
        </section>

        <section>
          <h3 className="mb-1 font-bold uppercase">3. Tempo certificado — {formatDate(s.periodo.inicio)} a {formatDate(s.periodo.fim)}</h3>
          <table className="w-full border-collapse">
            <thead><tr className="border-b border-black text-right"><th className="text-left">Ano</th><th>Dias brutos</th><th>Deduções</th><th>Dias líquidos</th></tr></thead>
            <tbody>{s.frequencia_anual.map((r) => (
              <tr key={r.ano} className="border-b text-right"><td className="text-left">{r.ano}</td><td>{formatInt(r.dias_brutos)}</td><td>{formatInt(r.deducoes)}</td><td>{formatInt(r.dias_liquidos)}</td></tr>
            ))}</tbody>
            <tfoot><tr className="border-t-2 border-black text-right font-bold"><td className="text-left">Total</td><td>{formatInt(s.totais.dias_brutos)}</td><td>{formatInt(s.totais.deducoes)}</td><td>{formatInt(s.totais.dias_liquidos)}</td></tr></tfoot>
          </table>
          <p className="mt-1"><b>Tempo líquido:</b> {formatInt(s.totais.dias_liquidos)} dias, correspondentes a {s.totais.liquido_texto} ({s.totais.anos_decimais} anos).</p>
        </section>

        {s.remuneracoes.length > 0 && (
          <section>
            <h3 className="mb-1 font-bold uppercase">4. Relação das remunerações de contribuição (a partir de 07/1994)</h3>
            <div className="columns-4 gap-4 text-[11px]">
              {s.remuneracoes.map((r) => <div key={r.competencia} className="flex justify-between"><span>{r.competencia}</span><span>{formatCurrency(r.valor)}</span></div>)}
            </div>
          </section>
        )}

        <section>
          <h3 className="mb-1 font-bold uppercase">Destinação</h3>
          <p>Certidão destinada a <b>{s.destino}</b>, para fins de {s.finalidade.toLowerCase()}.</p>
          <ul className="mt-1 list-disc pl-5">{s.observacoes.map((o) => <li key={o}>{o}</li>)}</ul>
        </section>

        <footer className="pt-10">
          <div className="grid grid-cols-2 gap-10 text-center">
            <div className="border-t border-black pt-1">Responsável pela emissão<br />{s.emitida_por}</div>
            <div className="border-t border-black pt-1">Dirigente da unidade gestora (homologação)</div>
          </div>
          <p className="mt-6 text-[10px] text-gray-600">
            {s.instituicao.cidade}/{s.instituicao.uf}, emitida em {formatDateTime(s.emitida_em)} · Código de conferência (SHA-256): {c.sha256}
          </p>
        </footer>
      </article>

      <ConfirmDialog
        open={cancelling}
        onOpenChange={setCancelling}
        title={`Cancelar CTC ${c.code}`}
        description="A certidão não é excluída: fica no histórico como cancelada, com o motivo."
        confirmLabel="Cancelar CTC"
        destructive
        requireJustification
        onConfirm={async (j) => {
          try {
            await api(`previdencia/ctc/${id}/cancel`, { method: "POST", body: { justification: j } });
            toast.success("CTC cancelada.");
            mutate();
          } catch (err) {
            toast.error((err as Error).message);
            throw err;
          }
        }}
      />
    </>
  );
}
