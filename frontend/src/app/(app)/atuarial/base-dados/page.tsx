"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, Download, FileArchive, Loader2, Play } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api, download, fetcher, type Paginated } from "@/lib/api";
import { formatDateTime, formatInt } from "@/lib/format";
import type { ActuarialBase } from "@/lib/types";

type Variable = { nome: string; descricao: string; tipo: string; formato: string; categorias: string; observacao: string };
type Layout = {
  codigo: string; nome: string; fonte: string; observacao: string;
  arquivos: { chave: string; arquivo: string; rotulo: string; baixas: boolean; variaveis: Variable[] }[];
};

const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const FOLDERS: Record<string, string> = {
  FUNDO_CAPITALIZACAO: "Fundo em capitalização (Previdenciário)",
  FUNDO_REPARTICAO: "Fundo em repartição (Financeiro)",
  COMPLEMENTAR_COMPRA_VIDAS: "Complementar — Compra de Vidas",
};

export default function ActuarialBasePage() {
  return (
    <RequirePermission module="atuarial.base">
      <Screen />
    </RequirePermission>
  );
}

function Screen() {
  const { can, me } = useSession();
  const list = useSWR<Paginated<ActuarialBase>>("actuarial-bases?page_size=50", fetcher);
  const [detail, setDetail] = useState<ActuarialBase | null>(null);

  return (
    <>
      <PageHeader
        title="Base de Dados Atuarial"
        description="Geração da base cadastral para a avaliação atuarial no leiaute padrão da SPREV."
        breadcrumb={[{ label: "Avaliação Atuarial" }, { label: "Base de Dados (SPREV)" }]}
      />
      <div className="grid gap-4 xl:grid-cols-5">
        {can("atuarial.base", "incluir") && (
          <Generate lifePurchase={!!me?.institution?.life_purchase_enabled} onGenerated={(b) => { list.mutate(); setDetail(b); }} />
        )}
        <Structure lifePurchase={!!me?.institution?.life_purchase_enabled} />

        <Card className="xl:col-span-5">
          <CardHeader><CardTitle>Bases geradas</CardTitle></CardHeader>
          {list.error && <CardContent><ErrorState error={list.error} /></CardContent>}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Data-base</TableHead>
                <TableHead>Gerada em</TableHead>
                <TableHead>Por</TableHead>
                <TableHead className="text-right">Registros</TableHead>
                <TableHead>Pendências</TableHead>
                <TableHead>Hash (SHA-256)</TableHead>
                <TableHead className="w-32" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.isLoading && <LoadingRows cols={7} rows={2} />}
              {list.data?.results.map((b) => (
                <TableRow key={b.id} className="cursor-pointer" onClick={() => setDetail(b)}>
                  <TableCell className="font-semibold">
                    {b.data_base}
                    {b.life_purchase_enabled && <Badge variant="info" className="ml-2">Compra de Vidas</Badge>}
                  </TableCell>
                  <TableCell>{formatDateTime(b.created_at)}</TableCell>
                  <TableCell>{b.created_by_name || "—"}</TableCell>
                  <TableCell className="text-right tabular">{formatInt(totalRecords(b))}</TableCell>
                  <TableCell>
                    {b.pendencias.length ? <Badge variant="warning">{b.pendencias.length} pendência(s)</Badge> : <Badge variant="success">Nenhuma</Badge>}
                  </TableCell>
                  <TableCell className="font-mono text-2xs text-muted-foreground" title={b.file_sha256}>{b.file_sha256.slice(0, 16)}…</TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {can("atuarial.base", "exportar") && <DownloadButton base={b} />}
                  </TableCell>
                </TableRow>
              ))}
              {list.data && list.data.results.length === 0 && <EmptyRow cols={7} text="Nenhuma base gerada ainda." />}
            </TableBody>
          </Table>
          <p className="border-t px-4 py-2.5 text-2xs text-muted-foreground">
            Cada geração fica guardada com o arquivo e o hash SHA-256 — nada é sobrescrito, para conferência do atuário e dos órgãos de controle.
          </p>
        </Card>

        <Dictionary />
      </div>
      {detail && <DetailDialog base={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

function totalRecords(b: ActuarialBase) {
  // O complementar repete vidas já contadas no fundo em capitalização
  return Object.entries(b.summary)
    .filter(([folder]) => folder !== "COMPLEMENTAR_COMPRA_VIDAS")
    .reduce((s, [, files]) => s + Object.values(files).reduce((a, n) => a + n, 0), 0);
}

function Generate({ lifePurchase, onGenerated }: { lifePurchase: boolean; onGenerated: (b: ActuarialBase) => void }) {
  const now = new Date();
  const [form, setForm] = useState({ reference_month: String(now.getMonth() + 1), reference_year: String(now.getFullYear()), notes: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      const base = await api<ActuarialBase>("actuarial-bases", {
        method: "POST",
        body: { reference_month: Number(form.reference_month), reference_year: Number(form.reference_year), notes: form.notes },
      });
      toast.success(`Base atuarial ${base.data_base} gerada.`);
      onGenerated(base);
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="xl:col-span-2">
      <CardHeader><CardTitle>Gerar nova base</CardTitle></CardHeader>
      <form onSubmit={submit}>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <FormField label="Mês da data-base" htmlFor="ab-month" required error={errors.reference_month}>
            <Select id="ab-month" value={form.reference_month} onChange={(e) => setForm({ ...form, reference_month: e.target.value })}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </Select>
          </FormField>
          <FormField label="Ano" htmlFor="ab-year" required error={errors.reference_year}>
            <Input id="ab-year" type="number" min={1990} max={now.getFullYear()} value={form.reference_year} onChange={(e) => setForm({ ...form, reference_year: e.target.value })} required />
          </FormField>
          <FormField label="Observações" htmlFor="ab-notes" error={errors.notes} className="sm:col-span-2">
            <Textarea id="ab-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Ex.: base para a avaliação atuarial de 2027" />
          </FormField>
          <p className="text-2xs text-muted-foreground sm:col-span-2">
            Inclui segurados vinculados na data-base e as baixas (desligamentos e óbitos) dos 12 meses anteriores.
            {lifePurchase && " As vidas da Compra de Vidas também são identificadas em arquivo complementar."}
          </p>
        </CardContent>
        <div className="flex justify-end border-t bg-muted/40 px-4 py-2.5">
          <Button type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Play />} Gerar base</Button>
        </div>
      </form>
    </Card>
  );
}

function Structure({ lifePurchase }: { lifePurchase: boolean }) {
  return (
    <Card className="self-start xl:col-span-3">
      <CardHeader><CardTitle>Como a base é organizada</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="flex gap-3">
          <FileArchive className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <div>
            <div className="font-semibold">Arquivo ZIP com uma pasta por fundo</div>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted-foreground">
              <li><strong className="text-foreground">FUNDO_CAPITALIZACAO</strong> — Plano Previdenciário: massa própria {lifePurchase && "+ Compra de Vidas "}(CO_TIPO_FUNDO = 1)</li>
              <li><strong className="text-foreground">FUNDO_REPARTICAO</strong> — Plano Financeiro (CO_TIPO_FUNDO = 2)</li>
              {lifePurchase && (
                <li>
                  <strong className="text-foreground">COMPLEMENTAR_COMPRA_VIDAS</strong> — somente as vidas transferidas, no mesmo
                  leiaute, mais a identificação de cada vida e os lotes. Essas vidas já estão no fundo em capitalização: não somar.
                </li>
              )}
            </ul>
          </div>
        </div>
        <p className="text-muted-foreground">
          Em cada pasta: Servidores, Aposentados, Pensionistas, Dependentes e as Baixas, exatamente no leiaute oficial
          (CSV com ponto e vírgula, decimal com vírgula, datas dd/mm/aaaa). O leiaute oficial não tem campo para Compra de
          Vidas e a SPREV não permite alterá-lo — por isso a identificação vai no arquivo complementar.
        </p>
        <div className="flex gap-2 rounded-md border border-warning-border bg-warning-soft px-3 py-2 text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Os cadastros de servidores, aposentados, pensionistas e dependentes chegam nas Fases 2, 4 e 5. Até lá, os arquivos
            saem só com o cabeçalho oficial e as pendências são listadas — nenhum dado é inventado.
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function DownloadButton({ base }: { base: ActuarialBase }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await download(`actuarial-bases/${base.id}/download`, base.file_name);
        } catch (err) {
          toast.error((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? <Loader2 className="animate-spin" /> : <Download />} Baixar
    </Button>
  );
}

function DetailDialog({ base, onClose }: { base: ActuarialBase; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Base atuarial — data-base {base.data_base}</DialogTitle>
          <DialogDescription>Gerada em {formatDateTime(base.created_at)} · {base.file_name}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {Object.entries(base.summary).map(([folder, files]) => (
            <div key={folder}>
              <div className="section-label mb-1.5">{FOLDERS[folder] ?? folder}</div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
                {Object.entries(files).map(([name, n]) => (
                  <div key={name} className="flex justify-between border-b border-dashed py-0.5">
                    <span className="text-muted-foreground">{name}</span>
                    <span className="font-semibold tabular">{formatInt(n)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
          <div>
            <div className="section-label mb-1.5">Pendências ({base.pendencias.length})</div>
            {base.pendencias.length ? (
              <ul className="list-disc space-y-1 pl-4 text-xs">{base.pendencias.map((p) => <li key={p}>{p}</li>)}</ul>
            ) : (
              <p className="text-xs text-muted-foreground">Nenhuma pendência.</p>
            )}
          </div>
          <div className="break-all font-mono text-2xs text-muted-foreground">SHA-256: {base.file_sha256}</div>
          {base.notes && <p className="text-xs">{base.notes}</p>}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

function Dictionary() {
  const { data, error } = useSWR<Layout>("actuarial-bases/layout", fetcher);
  return (
    <Card className="xl:col-span-5">
      <CardHeader>
        <CardTitle>Dicionário do leiaute SPREV</CardTitle>
        {data && <a href={data.fonte} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary hover:underline">Fonte oficial</a>}
      </CardHeader>
      <CardContent>
        {error && <ErrorState error={error} />}
        {data && (
          <>
            <p className="mb-2 text-2xs text-muted-foreground">{data.observacao}</p>
            <Tabs defaultValue={data.arquivos[0].chave}>
              <TabsList className="overflow-x-auto">
                {data.arquivos.map((a) => <TabsTrigger key={a.chave} value={a.chave}>{a.rotulo}</TabsTrigger>)}
              </TabsList>
              {data.arquivos.map((a) => (
                <TabsContent key={a.chave} value={a.chave}>
                  <div className="mb-2 text-2xs text-muted-foreground">Arquivo <span className="font-mono">{a.arquivo}.csv</span> · {a.variaveis.length} variáveis</div>
                  <div className="max-h-[420px] overflow-auto rounded-md border thin-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-10">#</TableHead>
                          <TableHead>Variável</TableHead>
                          <TableHead>Descrição</TableHead>
                          <TableHead>Tipo</TableHead>
                          <TableHead>Categorias / formato</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {a.variaveis.map((v, i) => (
                          <TableRow key={v.nome}>
                            <TableCell className="text-muted-foreground tabular">{i + 1}</TableCell>
                            <TableCell className="font-mono text-2xs font-semibold">{v.nome}</TableCell>
                            <TableCell className="text-xs">{v.descricao}</TableCell>
                            <TableCell className="text-xs">{v.tipo}</TableCell>
                            <TableCell className="whitespace-pre-line text-2xs text-muted-foreground">{[v.formato, v.categorias].filter(Boolean).join("\n")}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </TabsContent>
              ))}
            </Tabs>
          </>
        )}
      </CardContent>
    </Card>
  );
}
