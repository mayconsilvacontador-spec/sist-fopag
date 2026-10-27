"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, Pencil, Plus } from "lucide-react";

import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher } from "@/lib/api";
import { formatDate, formatInt } from "@/lib/format";
import { TIME_NATURE } from "@/lib/options";
import type { Averbacao, TimeReport } from "@/lib/types";

const TOTALS: [keyof TimeReport["totais"], string][] = [
  ["contribuicao", "Tempo de contribuição"], ["servico_publico", "Serviço público"], ["magisterio", "Magistério"],
  ["carreira", "Carreira"], ["cargo", "Cargo atual"], ["especial", "Atividade especial"],
];

const AVERBACAO_FIELDS: FieldDef[] = [
  { name: "nature", label: "Natureza do tempo", type: "select", required: true, options: TIME_NATURE, wide: true },
  { name: "issuer", label: "Órgão / empresa emissora", required: true, wide: true },
  { name: "issuer_cnpj", label: "CNPJ do emissor", type: "cnpj" },
  { name: "certificate_number", label: "Nº da certidão (CTC / CNIS)" },
  { name: "certificate_date", label: "Data da certidão", type: "date" },
  { name: "start_date", label: "Início do período", type: "date", required: true },
  { name: "end_date", label: "Fim do período", type: "date", required: true },
  { name: "certified_days", label: "Dias líquidos certificados", type: "number", required: true, hint: "Total da certidão, já sem faltas." },
  { name: "magisterio", label: "Exercício de magistério", type: "checkbox" },
  { name: "special_activity", label: "Atividade especial (insalubre)", type: "checkbox" },
  { name: "conversion_extra_days", label: "Acréscimo por conversão de tempo especial (dias)", type: "number", hint: "Só para períodos até 12/11/2019." },
  { name: "act_number", label: "Ato de averbação" },
  { name: "act_date", label: "Data do ato", type: "date" },
  { name: "comprev", label: "Sujeito à COMPREV", type: "checkbox" },
  { name: "active", label: "Averbação ativa", type: "checkbox" },
  { name: "notes", label: "Observações", type: "textarea" },
];

export function TempoPanel({ personId, canEdit }: { personId: string; canEdit: boolean }) {
  const [on, setOn] = useState("");
  const { data, error, mutate } = useSWR<TimeReport>(`previdencia/tempo/${personId}${on ? `?data=${on}` : ""}`, fetcher);
  const av = useSWR<Averbacao[]>(`previdencia/averbacoes?person=${personId}`, fetcher);
  const [editing, setEditing] = useState<Averbacao | "new" | null>(null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <FormField label="Apurar até" htmlFor="tempo-on" hint="Vazio = hoje. Datas futuras projetam o vínculo ativo.">
          <Input id="tempo-on" type="date" value={on} onChange={(e) => setOn(e.target.value)} className="w-44" />
        </FormField>
      </div>
      {error && <ErrorState error={error} />}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {TOTALS.map(([k, label]) => (
          <div key={k} className="rounded-md border bg-card p-3">
            <div className="section-label">{label}</div>
            <div className="mt-1 text-sm font-semibold">{data ? data.totais[k].texto : "…"}</div>
            <div className="text-2xs text-muted-foreground tabular">{data ? `${formatInt(data.totais[k].dias)} dias` : ""}</div>
          </div>
        ))}
      </div>

      {data && data.avisos.length > 0 && (
        <div className="flex gap-2 rounded-md border border-warning-border bg-warning-soft px-3 py-2 text-xs text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <ul className="space-y-0.5">{data.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      )}

      <div>
        <div className="section-label mb-1.5">Períodos apurados</div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Período</TableHead><TableHead>Natureza</TableHead><TableHead>Origem</TableHead>
              <TableHead className="text-right">Brutos</TableHead><TableHead className="text-right">Deduções</TableHead>
              <TableHead className="text-right">Concomitância</TableHead><TableHead className="text-right">Líquidos</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={7} rows={2} />}
            {data?.periodos.map((p, i) => (
              <TableRow key={i}>
                <TableCell className="whitespace-nowrap text-xs">{formatDate(p.inicio)} a {p.ativo ? <Badge variant="success">ativo</Badge> : formatDate(p.fim)}</TableCell>
                <TableCell className="text-xs">{p.natureza} — {p.natureza_display}
                  <div className="mt-0.5 space-x-1">{p.magisterio && <Badge>Magistério</Badge>}{p.especial && <Badge variant="warning">Especial</Badge>}{p.servico_publico && <Badge variant="info">Serv. público</Badge>}</div>
                </TableCell>
                <TableCell className="text-xs">{p.descricao}{p.avisos.map((a) => <div key={a} className="text-2xs text-warning">{a}</div>)}</TableCell>
                <TableCell className="text-right tabular">{formatInt(p.dias_brutos)}</TableCell>
                <TableCell className="text-right tabular">{p.deducoes ? `−${formatInt(p.deducoes)}` : "—"}</TableCell>
                <TableCell className="text-right tabular">{p.concomitancia ? <span className="text-warning">−{formatInt(p.concomitancia)}</span> : "—"}</TableCell>
                <TableCell className="text-right font-semibold tabular">{formatInt(p.dias_liquidos + p.acrescimo_conversao)}</TableCell>
              </TableRow>
            ))}
            {data?.periodos.length === 0 && <EmptyRow cols={7} text="Nenhum período. Cadastre o vínculo e as averbações." />}
          </TableBody>
        </Table>
        <p className="pt-1 text-2xs text-muted-foreground">
          Dias corridos incluindo início e fim (365 dias = 1 ano). Afastamentos marcados no histórico funcional como “não conta tempo” são deduzidos.
          Sobreposição de períodos é cortada (vedada a contagem em dobro).
        </p>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <div className="section-label">Averbações (tempo de outros regimes e órgãos)</div>
          {canEdit && <Button size="sm" variant="outline" onClick={() => setEditing("new")}><Plus /> Nova averbação</Button>}
        </div>
        <Table>
          <TableHeader>
            <TableRow><TableHead>Emissor / certidão</TableHead><TableHead>Natureza</TableHead><TableHead>Período</TableHead><TableHead className="text-right">Dias certificados</TableHead><TableHead>Situação</TableHead><TableHead className="w-10" /></TableRow>
          </TableHeader>
          <TableBody>
            {av.data?.map((a) => (
              <TableRow key={a.id} className={a.active ? "" : "opacity-60"}>
                <TableCell><div className="font-medium">{a.issuer}</div><div className="text-2xs text-muted-foreground">{a.certificate_number ? `Certidão ${a.certificate_number}` : "Sem nº de certidão"}{a.certificate_date ? ` de ${formatDate(a.certificate_date)}` : ""}</div></TableCell>
                <TableCell className="text-xs">{a.nature} — {a.nature_display}</TableCell>
                <TableCell className="text-xs">{formatDate(a.start_date)} a {formatDate(a.end_date)}</TableCell>
                <TableCell className="text-right tabular">{formatInt(a.certified_days)}{a.conversion_extra_days ? ` + ${a.conversion_extra_days}` : ""}</TableCell>
                <TableCell>{a.active ? <Badge variant="success">Ativa</Badge> : <Badge variant="neutral">Inativa</Badge>}</TableCell>
                <TableCell>{canEdit && <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing(a)} aria-label="Editar"><Pencil /></Button>}</TableCell>
              </TableRow>
            ))}
            {av.data?.length === 0 && <EmptyRow cols={6} text="Nenhuma averbação." />}
          </TableBody>
        </Table>
      </div>

      {editing && (
        <FormDialog
          size="lg"
          title={editing === "new" ? "Nova averbação" : `Averbação — ${editing.issuer}`}
          description="Informe os dados exatamente como constam na certidão (CTC do RPPS de origem ou do INSS)."
          fields={AVERBACAO_FIELDS}
          initial={editing === "new" ? { nature: "01", comprev: true, active: true, conversion_extra_days: 0 } : (editing as unknown as Record<string, unknown>)}
          onClose={() => setEditing(null)}
          submit={async (body) => {
            const payload = { ...body, person: personId, conversion_extra_days: body.conversion_extra_days ?? 0 };
            if (editing === "new") await api("previdencia/averbacoes", { method: "POST", body: payload });
            else await api(`previdencia/averbacoes/${editing.id}`, { method: "PATCH", body: payload });
            toast.success("Averbação salva.");
            av.mutate();
            mutate();
          }}
        />
      )}
    </div>
  );
}
