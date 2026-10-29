"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { FileSpreadsheet, FileText, Loader2, Play, Printer } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { ErrorState } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, download, fetcher } from "@/lib/api";
import { formatCurrency, formatDate, formatDateTime, formatInt } from "@/lib/format";
import { cn } from "@/lib/utils";

type Filter = { key: string; label: string; type: "competencia" | "ano" | "data" | "select"; default?: string; options?: [string, string][]; options_url?: string };
type Meta = { codigo: string; modulo: string; titulo: string; descricao: string; filtros: Filter[]; paisagem: boolean };
type Column = { key: string; label: string; tipo: "text" | "int" | "money" | "date" | "percent" | "bool" };
type Result = Meta & {
  colunas: Column[]; linhas: Record<string, unknown>[]; totais: Record<string, unknown>; observacoes: string[];
  instituicao: string; gerado_em: string; parametros: Record<string, string>;
};

/** Valores padrão dos filtros (resolvidos na tela para mostrar ao usuário o que será usado). */
function defaultValue(f: Filter): string {
  const now = new Date();
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  switch (f.default) {
    case "atual": return String(now.getFullYear());
    case "atual+5": return String(now.getFullYear() + 5);
    case "inicio_ano": return `${now.getFullYear()}-01-01`;
    case "hoje": return iso(now);
    case "mes_anterior": { const d = new Date(now.getFullYear(), now.getMonth() - 1, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; }
    case "ultima_folha": return ""; // o servidor usa a última folha calculada
    default: return f.default ?? "";
  }
}

function fmt(v: unknown, tipo: Column["tipo"]): string {
  if (v === null || v === undefined || v === "") return "";
  switch (tipo) {
    case "money": return formatCurrency(String(v));
    case "int": return typeof v === "number" ? formatInt(v) : String(v);
    case "date": return formatDate(String(v));
    case "percent": return `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
    case "bool": return v ? "Sim" : "Não";
    default: return String(v);
  }
}

export function ReportsPage({ module, title, description }: { module: string; title: string; description: string }) {
  return (
    <RequirePermission module={module}>
      <Reports module={module} title={title} description={description} />
    </RequirePermission>
  );
}

function Reports({ module, title, description }: { module: string; title: string; description: string }) {
  const { can } = useSession();
  const router = useRouter();
  const search = useSearchParams();
  const { data: list, error } = useSWR<Meta[]>(`reports?modulo=${module}`, fetcher);
  const code = search.get("r") || list?.[0]?.codigo;
  const meta = list?.find((r) => r.codigo === code);
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (meta) setValues(Object.fromEntries(meta.filtros.map((f) => [f.key, defaultValue(f)])));
    setResult(null);
  }, [meta]);

  const query = useMemo(() => {
    // modulo = tela de onde o relatório foi aberto (o mesmo relatório pode aparecer em mais de uma tela)
    const q = new URLSearchParams({ modulo: module });
    Object.entries(values).forEach(([k, v]) => { if (v) q.set(k, v); });
    return q.toString();
  }, [values, module]);

  const run = async () => {
    if (!meta) return;
    setBusy(true);
    try {
      setResult(await api<Result>(`reports/${meta.codigo}${query ? `?${query}` : ""}`));
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const exportAs = (formato: "xlsx" | "csv") => {
    if (!meta) return;
    download(`reports/${meta.codigo}/export?formato=${formato}${query ? `&${query}` : ""}`, `${meta.codigo}.${formato}`)
      .catch((e) => toast.error((e as Error).message));
  };
  const canExport = can(module, "exportar");

  return (
    <>
      <div className="print:hidden">
        <PageHeader title={title} description={description} breadcrumb={[{ label: "Relatórios" }, { label: title }]} />
      </div>
      {error && <ErrorState error={error} />}
      <div className="grid gap-4 xl:grid-cols-12">
        <Card className="self-start xl:col-span-3 print:hidden">
          <CardHeader><CardTitle>Relatórios</CardTitle></CardHeader>
          <div className="divide-y">
            {list?.map((r) => (
              <button key={r.codigo} type="button" onClick={() => router.replace(`?r=${r.codigo}`)}
                className={cn("block w-full px-4 py-3 text-left hover:bg-muted/60", r.codigo === code && "bg-primary-soft")}>
                <div className={cn("text-[13.5px] font-medium", r.codigo === code ? "text-primary-strong" : "text-foreground")}>{r.titulo}</div>
                <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{r.descricao}</div>
              </button>
            ))}
            {list && list.length === 0 && <div className="px-4 py-6 text-center text-xs text-muted-foreground">Nenhum relatório disponível para o seu perfil.</div>}
          </div>
        </Card>

        <div className="space-y-4 xl:col-span-9">
          {meta && (
            <Card className="print:hidden">
              <CardHeader><CardTitle>{meta.titulo}</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">{meta.descricao}</p>
                <div className="flex flex-wrap items-end gap-3">
                  {meta.filtros.map((f) => (
                    <label key={f.key} className="space-y-1 text-xs">
                      <span className="block font-medium">{f.label}</span>
                      {f.type === "select" ? (
                        <FilterSelect f={f} value={values[f.key] ?? ""} onChange={(v) => setValues((s) => ({ ...s, [f.key]: v }))} />
                      ) : (
                        <Input type={f.type === "data" ? "date" : f.type === "competencia" ? "month" : "number"}
                          value={values[f.key] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                          className="h-9 w-[160px]" placeholder={f.default === "ultima_folha" ? "última folha" : undefined} />
                      )}
                    </label>
                  ))}
                  <Button onClick={run} disabled={busy} className="h-9">{busy ? <Loader2 className="animate-spin" /> : <Play />} Gerar relatório</Button>
                  {result && (
                    <>
                      {canExport && <Button variant="outline" className="h-9" onClick={() => exportAs("xlsx")}><FileSpreadsheet /> Excel</Button>}
                      {canExport && <Button variant="outline" className="h-9" onClick={() => exportAs("csv")}><FileText /> CSV</Button>}
                      <Button variant="outline" className="h-9" onClick={() => window.print()}><Printer /> Imprimir</Button>
                    </>
                  )}
                </div>
                {meta.codigo === "previsao-aposentadorias" && <p className="text-2xs text-muted-foreground">Este relatório calcula todas as regras de cada servidor e pode levar alguns segundos.</p>}
              </CardContent>
            </Card>
          )}

          {result && <ResultTable r={result} />}
          {!result && meta && !busy && (
            <Card className="print:hidden"><CardContent className="py-12 text-center text-sm text-muted-foreground">Escolha os filtros e clique em <b>Gerar relatório</b>.</CardContent></Card>
          )}
        </div>
      </div>
    </>
  );
}

/** Lista de opções fixa ou carregada do sistema (ex.: campanhas de prova de vida). */
function FilterSelect({ f, value, onChange }: { f: Filter; value: string; onChange: (v: string) => void }) {
  const { data } = useSWR<{ results?: { id: string; name: string }[] } | { id: string; name: string }[]>(
    f.options_url ? `${f.options_url}?page_size=100` : null, fetcher);
  const remote = Array.isArray(data) ? data : data?.results ?? [];
  const options: [string, string][] = [...(f.options ?? []), ...remote.map((r) => [r.id, r.name] as [string, string])];
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} className="h-9 min-w-[160px]">
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </Select>
  );
}

function ResultTable({ r }: { r: Result }) {
  const filters = r.filtros.map((f) => {
    const v = r.parametros[f.key];
    const label = f.type === "select" ? (f.options?.find(([k]) => k === (v ?? ""))?.[1] ?? (v ? "selecionada" : undefined)) : v;
    return label ? `${f.label}: ${f.type === "data" ? formatDate(String(label)) : label}` : null;
  }).filter(Boolean);
  const right = (t: Column["tipo"]) => ["int", "money", "percent"].includes(t);
  return (
    <Card className="print:border-0 print:shadow-none">
      <div className="border-b px-4 py-3">
        <div className="hidden text-xs text-muted-foreground print:block">{r.instituicao}</div>
        <div className="text-[15px] font-semibold text-primary-strong">{r.titulo}</div>
        <div className="text-xs text-muted-foreground">
          {filters.length ? filters.join(" · ") : "Sem filtros"} · {r.linhas.length} linha(s) · gerado em {formatDateTime(r.gerado_em)}
        </div>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>{r.colunas.map((c) => <TableHead key={c.key} className={cn(right(c.tipo) && "text-right")}>{c.label}</TableHead>)}</TableRow>
          </TableHeader>
          <TableBody>
            {r.linhas.map((row, i) => (
              <TableRow key={i} className={row._subtotal ? "bg-muted/40 font-semibold" : undefined}>
                {r.colunas.map((c) => <TableCell key={c.key} className={cn(right(c.tipo) && "text-right tabular", "whitespace-nowrap")}>{fmt(row[c.key], c.tipo)}</TableCell>)}
              </TableRow>
            ))}
            {r.linhas.length === 0 && (
              <TableRow><TableCell colSpan={r.colunas.length} className="py-10 text-center text-muted-foreground">Nenhum registro para os filtros escolhidos.</TableCell></TableRow>
            )}
            {Object.keys(r.totais).length > 0 && r.linhas.length > 0 && (
              <TableRow className="bg-muted/60 font-semibold">
                {r.colunas.map((c, i) => (
                  <TableCell key={c.key} className={cn(right(c.tipo) && "text-right tabular", "whitespace-nowrap")}>
                    {c.key in r.totais ? fmt(r.totais[c.key], typeof r.totais[c.key] === "string" && !right(c.tipo) ? "text" : c.tipo) : i === 0 ? "Total" : ""}
                  </TableCell>
                ))}
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      {r.observacoes.length > 0 && (
        <div className="space-y-0.5 border-t px-4 py-2.5 text-xs text-muted-foreground">{r.observacoes.map((o) => <p key={o}>{o}</p>)}</div>
      )}
    </Card>
  );
}
