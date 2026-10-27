"use client";

import { useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Download, FileUp, Loader2, Plus, Trash2 } from "lucide-react";

import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { FormDialog } from "@/components/shared/registry-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, download, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { ContributionSalaryRow, EmploymentLink } from "@/lib/types";

export function SalariosPanel({ personId, canEdit, canExport }: { personId: string; canEdit: boolean; canExport: boolean }) {
  const { data, isLoading, mutate } = useSWR<ContributionSalaryRow[]>(`previdencia/salarios?person=${personId}`, fetcher);
  const links = useSWR<Paginated<EmploymentLink>>(`employment-links?person=${personId}&page_size=20`, fetcher);
  const [adding, setAdding] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const totals = useMemo(() => {
    const months = new Set(data?.map((s) => s.competence));
    return { meses: months.size, rpps: data?.filter((s) => s.regime === "RPPS").length ?? 0, rgps: data?.filter((s) => s.regime === "RGPS").length ?? 0 };
  }, [data]);

  const importCsv = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("person", personId);
      fd.append("file", file);
      const res = await fetch("/api/backend/previdencia/salarios/import", { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Falha na importação.");
      toast.success(`${body.incluidos} incluído(s), ${body.atualizados} atualizado(s)${body.erros.length ? `, ${body.erros.length} linha(s) com erro` : ""}.`);
      if (body.erros.length) toast.error(body.erros.slice(0, 3).map((e: { linha: number; mensagem: string }) => `Linha ${e.linha}: ${e.mensagem}`).join(" · "));
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (s: ContributionSalaryRow) => {
    try {
      await api(`previdencia/salarios/${s.id}`, { method: "DELETE" });
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const link = links.data?.results[0];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">
          {totals.meses} competência(s) desde 07/1994 · {totals.rpps} RPPS · {totals.rgps} RGPS
        </div>
        <div className="flex flex-wrap gap-2">
          {canEdit && (
            <>
              <input ref={fileRef} type="file" accept=".csv,.txt" className="hidden" onChange={importCsv} />
              <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}>
                {busy ? <Loader2 className="animate-spin" /> : <FileUp />} Importar CSV
              </Button>
              <Button size="sm" variant="outline" onClick={() => setAdding(true)}><Plus /> Incluir competência</Button>
            </>
          )}
          {canExport && <Button size="sm" onClick={() => setExporting(true)} disabled={!data?.length}><Download /> SalContr.txt (TCE-RJ)</Button>}
        </div>
      </div>
      <p className="text-2xs text-muted-foreground">
        CSV: <code>competencia;valor;regime;vinculo</code> — ex.: <code>07/1994;1.234,56;RPPS;Prefeitura</code> (regime e vínculo opcionais).
        Valores da época, sem correção. Competência repetida é atualizada.
      </p>
      <div className="max-h-[480px] overflow-auto rounded-md border thin-scroll">
        <Table>
          <TableHeader><TableRow><TableHead>Competência</TableHead><TableHead>Regime</TableHead><TableHead>Vínculo / empregador</TableHead><TableHead className="text-right">Salário de contribuição</TableHead><TableHead>Origem</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
          <TableBody>
            {isLoading && <LoadingRows cols={6} rows={3} />}
            {data?.map((s) => (
              <TableRow key={s.id}>
                <TableCell className="tabular">{s.competencia}</TableCell>
                <TableCell><Badge variant={s.regime === "RPPS" ? "default" : "info"}>{s.regime}</Badge></TableCell>
                <TableCell className="text-xs">{s.source_label || "—"}</TableCell>
                <TableCell className="text-right tabular">{formatCurrency(s.amount)}</TableCell>
                <TableCell className="text-2xs text-muted-foreground">{s.origin}</TableCell>
                <TableCell>{canEdit && <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => remove(s)} aria-label="Excluir"><Trash2 /></Button>}</TableCell>
              </TableRow>
            ))}
            {data?.length === 0 && <EmptyRow cols={6} text="Nenhum salário de contribuição. Importe o arquivo do RH (deste servidor em Importar CSV, ou de vários em Importar lote, abaixo) ou inclua competência por competência." />}
          </TableBody>
        </Table>
      </div>

      {adding && (
        <FormDialog
          title="Incluir competência"
          description="Aqui entra só a BASE (salário de contribuição usado na média). Para registrar também a alíquota e o valor descontado do servidor, use “Lançar competência” no Controle da contribuição, acima — ele já inclui a base aqui."
          fields={[
            { name: "competence", label: "Competência (mês/ano)", type: "date", required: true, hint: "Qualquer dia do mês." },
            { name: "regime", label: "Regime", type: "select", required: true, options: [{ value: "RPPS", label: "RPPS" }, { value: "RGPS", label: "RGPS (INSS)" }] },
            { name: "amount", label: "Salário de contribuição (R$)", type: "money", required: true },
            { name: "source_label", label: "Vínculo / empregador", wide: true },
          ]}
          initial={{ regime: "RPPS" }}
          onClose={() => setAdding(false)}
          submit={async (body) => { await api("previdencia/salarios", { method: "POST", body: { ...body, person: personId } }); toast.success("Competência incluída."); mutate(); }}
        />
      )}
      {exporting && (
        <FormDialog
          title="Gerar SalContr.txt — Deliberação TCE-RJ 260"
          description="Único arquivo que o FATIMA aceita importar. Os códigos SIGFIS estão no cadastro do órgão."
          fields={[
            { name: "ug", label: "Unidade gestora (código SIGFIS)", type: "digits", maxLength: 4, required: true },
            { name: "orgao", label: "Órgão (código SIGFIS)", type: "digits", maxLength: 4, required: true },
            { name: "matricula", label: "Matrícula", required: true, maxLength: 10 },
            { name: "processo", label: "Nº do processo no órgão de origem", required: true, maxLength: 20 },
            { name: "tipo_ato", label: "Tipo do ato", type: "select", required: true, options: [{ value: 1, label: "1 – Aposentadoria" }, { value: 4, label: "4 – Pensão civil" }] },
          ]}
          initial={{ tipo_ato: 1, matricula: link?.registration ?? "" }}
          submitLabel="Baixar arquivo"
          onClose={() => setExporting(false)}
          submit={async (body) => {
            await download(`previdencia/salarios/salcontr${qs({ person: personId, ...(body as Record<string, string>) })}`, "SalContr.txt");
          }}
        />
      )}
    </div>
  );
}
