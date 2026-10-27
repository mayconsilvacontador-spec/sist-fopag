"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CheckCircle2, FileUp, Loader2, Trash2 } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, fetcher, type Paginated } from "@/lib/api";
import { formatDateTime, formatInt } from "@/lib/format";
import type { ImportBatchRow, ImportReport } from "@/lib/types";

const RESUMO: [string, string][] = [
  ["pessoas_novas", "Pessoas novas"], ["pessoas_completadas", "Pessoas existentes completadas"],
  ["pessoas_sem_nome", "Pessoas sem nome (completar pela Receita)"], ["vinculos", "Vínculos de servidores"],
  ["vinculos_existentes", "Vínculos já existentes (ignorados)"], ["dependencias", "Dependências"],
  ["beneficios", "Aposentadorias e pensões (aguardam a Fase 4)"], ["entes_criados", "Entes criados"],
  ["orgaos_criados", "Órgãos criados"], ["cargos_criados", "Cargos criados"],
];

export default function ImportPage() {
  return (
    <RequirePermission module="cadastros.importacao">
      <Importer />
    </RequirePermission>
  );
}

function Importer() {
  const { can } = useSession();
  const list = useSWR<Paginated<ImportBatchRow>>("imports?page_size=30", fetcher);
  const [current, setCurrent] = useState<ImportBatchRow | null>(null);
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<"confirm" | "discard" | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const validate = async () => {
    const fl = fileRef.current?.files;
    if (!fl?.length) { toast.error("Selecione os arquivos."); return; }
    if (!source.trim()) { toast.error("Informe o sistema ou órgão de origem."); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("source_system", source);
      Array.from(fl).forEach((f) => fd.append("files", f));
      const res = await fetch("/api/backend/imports", { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || Object.values(body).flat().join(" ") || "Falha na validação.");
      setCurrent(body);
      list.mutate();
      toast.success("Arquivos validados. Confira o relatório antes de confirmar.");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const act = async () => {
    if (!current || !confirm) return;
    try {
      const b = await api<ImportBatchRow>(`imports/${current.id}/${confirm}`, { method: "POST" });
      setCurrent(b);
      list.mutate();
      toast.success(confirm === "confirm" ? "Importação concluída." : "Lote descartado.");
    } catch (err) {
      toast.error((err as Error).message);
      throw err;
    }
  };

  return (
    <>
      <PageHeader
        title="Importação de segurados"
        description="Traga os cadastros de outros sistemas usando os arquivos da base atuarial no leiaute SPREV — formato que todo RPPS já gera."
        breadcrumb={[{ label: "Gestão de Cadastros" }, { label: "Importação" }]}
      />
      <div className="grid gap-4 xl:grid-cols-5">
        {can("cadastros.importacao", "incluir") && (
          <Card className="xl:col-span-3">
            <CardHeader><CardTitle>1. Enviar arquivos</CardTitle></CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <FormField label="Sistema / órgão de origem" htmlFor="imp-source" required hint="Ex.: Sistema XYZ da Prefeitura de ...">
                <Input id="imp-source" value={source} onChange={(e) => setSource(e.target.value)} />
              </FormField>
              <FormField label="Arquivos (CSV ou Excel)" htmlFor="imp-files" required hint="Pode enviar vários de uma vez.">
                <Input id="imp-files" ref={fileRef} type="file" multiple accept=".csv,.txt,.xlsx" className="py-1" />
              </FormField>
              <div className="sm:col-span-2">
                <Button onClick={validate} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <FileUp />} Validar arquivos</Button>
                <span className="ml-3 text-2xs text-muted-foreground">A validação não grava nada — você confere o relatório e depois confirma.</span>
              </div>
            </CardContent>
          </Card>
        )}
        <Card className="self-start xl:col-span-2">
          <CardHeader><CardTitle>Como funciona</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs text-muted-foreground">
            <p>Envie os arquivos <strong className="text-foreground">SERVIDORES, APOSENTADOS, PENSIONISTAS e DEPENDENTES</strong> da base atuarial (cabeçalho com os nomes das variáveis SPREV). O tipo é reconhecido pelo cabeçalho.</p>
            <ul className="list-disc space-y-1 pl-4">
              <li>Servidores viram pessoas + vínculos; órgãos e cargos que não existirem são criados.</li>
              <li>Aposentadorias e pensões ficam guardadas para implantação na folha (Fase 4).</li>
              <li>Pessoas já cadastradas (mesmo CPF) não são sobrescritas — só campos vazios são completados.</li>
              <li>O leiaute SPREV não traz nomes: se o arquivo tiver uma coluna <code>NOME</code>, ela é usada; senão, complete pela Receita.</li>
            </ul>
            <p className="pt-1"><strong className="text-foreground">Arquivos complementares (leiaute SIST)</strong> — podem ir no mesmo lote, junto com os do SPREV:</p>
            <ul className="list-disc space-y-1 pl-4">
              <li><code>PESSOAS_COMPLEMENTO</code>: filiação, RG, naturalidade, escolaridade, raça/cor, e-mail, celular, título de eleitor.</li>
              <li><code>ENDERECOS</code> e <code>CONTAS_BANCARIAS</code>: entram com vigência (o anterior é encerrado, nada é apagado).</li>
              <li><code>AVERBACOES_CTC</code>: tempo de INSS, outros RPPS e Forças Armadas, com nº e data da CTC.</li>
              <li><code>HISTORICO_FUNCIONAL</code>: nomeação, posse, progressões, faltas, licenças, cessões, abono (pela matrícula).</li>
            </ul>
          </CardContent>
        </Card>

        {current && (
          <Card className="xl:col-span-5">
            <CardHeader>
              <CardTitle>2. Relatório — {current.source_system} <Badge className="ml-2" variant={current.status === "IMPORTADO" ? "success" : current.status === "DESCARTADO" ? "neutral" : "warning"}>{current.status_display}</Badge></CardTitle>
              {current.status === "VALIDADO" && can("cadastros.importacao", "incluir") && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setConfirm("discard")}><Trash2 /> Descartar</Button>
                  <Button size="sm" onClick={() => setConfirm("confirm")}><CheckCircle2 /> Confirmar importação</Button>
                </div>
              )}
            </CardHeader>
            <CardContent>
              <ReportView report={current.status === "IMPORTADO" && "resumo" in current.result ? (current.result as ImportReport) : current.report} />
            </CardContent>
          </Card>
        )}

        <Card className="xl:col-span-5">
          <CardHeader><CardTitle>Importações anteriores</CardTitle></CardHeader>
          <Table>
            <TableHeader><TableRow><TableHead>Data</TableHead><TableHead>Origem</TableHead><TableHead>Arquivos</TableHead><TableHead>Situação</TableHead><TableHead>Por</TableHead></TableRow></TableHeader>
            <TableBody>
              {list.isLoading && <LoadingRows cols={5} rows={2} />}
              {list.data?.results.map((b) => (
                <TableRow key={b.id} className="cursor-pointer" onClick={() => setCurrent(b)}>
                  <TableCell>{formatDateTime(b.created_at)}</TableCell>
                  <TableCell className="font-medium">{b.source_system}</TableCell>
                  <TableCell className="text-xs">{b.files.map((f) => f.nome).join(", ")}</TableCell>
                  <TableCell><Badge variant={b.status === "IMPORTADO" ? "success" : b.status === "DESCARTADO" ? "neutral" : "warning"}>{b.status_display}</Badge></TableCell>
                  <TableCell>{b.created_by_name}</TableCell>
                </TableRow>
              ))}
              {list.data?.results.length === 0 && <EmptyRow cols={5} text="Nenhuma importação." />}
            </TableBody>
          </Table>
        </Card>
      </div>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={confirm === "confirm" ? "Confirmar importação" : "Descartar lote"}
        description={confirm === "confirm"
          ? "As linhas sem erro serão gravadas no Cadastro Único. As linhas com erro ficam de fora — corrija o arquivo e importe de novo."
          : "Nada será gravado. Os arquivos enviados ficam guardados no histórico."}
        confirmLabel={confirm === "confirm" ? "Importar" : "Descartar"}
        destructive={confirm === "discard"}
        onConfirm={act}
      />
    </>
  );
}

function ReportView({ report }: { report: ImportReport }) {
  return (
    <div className="space-y-4">
      <Table>
        <TableHeader><TableRow><TableHead>Arquivo</TableHead><TableHead>Tipo</TableHead><TableHead className="text-right">Linhas</TableHead><TableHead className="text-right">Válidas</TableHead><TableHead className="text-right">Com erro</TableHead></TableRow></TableHeader>
        <TableBody>
          {report.arquivos.map((a) => (
            <TableRow key={a.nome}>
              <TableCell className="font-medium">{a.nome}</TableCell>
              <TableCell>{a.tipo}</TableCell>
              <TableCell className="text-right tabular">{formatInt(a.linhas)}</TableCell>
              <TableCell className="text-right tabular text-success">{formatInt(a.validas)}</TableCell>
              <TableCell className="text-right tabular">{a.erros ? <span className="font-semibold text-critical">{formatInt(a.erros)}</span> : "0"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2 xl:grid-cols-3">
        {RESUMO.map(([k, label]) => (
          <div key={k} className="flex justify-between border-b border-dashed py-1">
            <span className="text-muted-foreground">{label}</span>
            <span className="font-semibold tabular">{formatInt(report.resumo[k] ?? 0)}</span>
          </div>
        ))}
      </div>

      <Tabs defaultValue={report.total_erros ? "erros" : "avisos"}>
        <TabsList>
          <TabsTrigger value="erros">Erros ({formatInt(report.total_erros)})</TabsTrigger>
          <TabsTrigger value="avisos">Avisos ({formatInt(report.total_avisos)})</TabsTrigger>
        </TabsList>
        {(["erros", "avisos"] as const).map((k) => (
          <TabsContent key={k} value={k}>
            <div className="max-h-80 overflow-auto rounded-md border thin-scroll">
              <Table>
                <TableHeader><TableRow><TableHead>Arquivo</TableHead><TableHead>Linha</TableHead><TableHead>CPF</TableHead><TableHead>Mensagem</TableHead></TableRow></TableHeader>
                <TableBody>
                  {report[k].map((m, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-xs">{m.arquivo}</TableCell>
                      <TableCell className="tabular">{m.linha}</TableCell>
                      <TableCell className="font-mono text-2xs">{m.cpf || "—"}</TableCell>
                      <TableCell className="text-xs">{m.mensagem}</TableCell>
                    </TableRow>
                  ))}
                  {report[k].length === 0 && <EmptyRow cols={4} text={k === "erros" ? "Nenhum erro." : "Nenhum aviso."} />}
                </TableBody>
              </Table>
            </div>
            {report[`total_${k}`] > report[k].length && (
              <p className="pt-1 text-2xs text-muted-foreground">Mostrando as primeiras {report[k].length} de {formatInt(report[`total_${k}`])} mensagens.</p>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
