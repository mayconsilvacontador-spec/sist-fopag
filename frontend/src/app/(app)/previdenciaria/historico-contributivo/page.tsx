"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { FileUp, Loader2 } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { PersonScopedPage } from "@/components/previdencia/person-scoped-page";
import { SalariosPanel } from "@/components/previdencia/salarios-panel";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetcher } from "@/lib/api";

export default function Page() {
  const { can } = useSession();
  return (
    <>
      <PersonScopedPage
        module="previdenciaria.historico_contributivo"
        title="Histórico Contributivo"
        description="Salários de contribuição mês a mês desde 07/1994 — base das médias e do arquivo SalContr.txt (Deliberação TCE-RJ 260)."
      >
        {(id) => (
          <SalariosPanel personId={id} canEdit={can("previdenciaria.historico_contributivo", "incluir")}
            canExport={can("previdenciaria.historico_contributivo", "exportar")} />
        )}
      </PersonScopedPage>
      {can("previdenciaria.historico_contributivo", "incluir") && <BatchImport />}
      {can("previdenciaria.historico_contributivo", "incluir") && <Factors />}
    </>
  );
}

function Factors() {
  const { data, mutate } = useSWR<{ mes: string; competencias: number }[]>("previdencia/fatores", fetcher);
  const [month, setMonth] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!month || !file) { toast.error("Informe o mês da tabela e o arquivo."); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("table_month", month);
      fd.append("file", file);
      const res = await fetch("/api/backend/previdencia/fatores", { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || Object.values(body).flat().join(" ") || "Falha.");
      toast.success(`${body.fatores} fator(es) importado(s)${body.erros.length ? `, ${body.erros.length} erro(s)` : ""}.`);
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mt-4">
      <CardHeader><CardTitle>Tabelas de atualização dos salários de contribuição</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-xs">
        <p className="text-muted-foreground">
          Fatores mensais publicados pelo Ministério da Previdência para atualizar os salários no cálculo da média. CSV com
          <code> competencia;fator</code> (ex.: <code>07/1994;7,123456</code>). Sem tabela, a média é estimada com valores nominais.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField label="Mês da tabela" htmlFor="ft-month"><Input id="ft-month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></FormField>
          <FormField label="Arquivo CSV" htmlFor="ft-file"><Input id="ft-file" ref={fileRef} type="file" accept=".csv,.txt" className="py-1" /></FormField>
          <div className="flex items-end"><Button onClick={upload} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <FileUp />} Importar tabela</Button></div>
        </div>
        <div>Tabelas cadastradas: {data?.length ? data.map((t) => `${t.mes} (${t.competencias})`).join(" · ") : "nenhuma"}</div>
      </CardContent>
    </Card>
  );
}

type BatchResult = { segurados: number; incluidos: number; atualizados: number; cpfs_nao_cadastrados: number; erros: { linha: number; mensagem: string }[] };

function BatchImport() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BatchResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) { toast.error("Escolha o arquivo."); return; }
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/backend/previdencia/salarios/import-lote", { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || Object.values(body).flat().join(" ") || "Falha na importação.");
      setResult(body);
      toast.success(`${body.segurados} segurado(s): ${body.incluidos} competência(s) incluída(s), ${body.atualizados} atualizada(s).`);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="mt-4">
      <CardHeader><CardTitle>Importar lote (vários segurados)</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-xs">
        <p className="text-muted-foreground">
          Arquivo com os salários de muitos servidores de uma vez (ex.: enviado pelo RH da Prefeitura). CSV com
          <code> cpf;competencia;valor;regime;vinculo</code> (ex.: <code>123.456.789-09;07/1994;1.234,56;RPPS;Prefeitura</code>).
          Regime e vínculo são opcionais. CPF ainda não cadastrado é listado e não é importado; competência repetida é atualizada.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField label="Arquivo CSV" htmlFor="lt-file" className="sm:col-span-2"><Input id="lt-file" ref={fileRef} type="file" accept=".csv,.txt" className="py-1" /></FormField>
          <div className="flex items-end"><Button onClick={upload} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <FileUp />} {busy ? "Importando…" : "Importar lote"}</Button></div>
        </div>
        {result && (
          <div className="rounded border bg-muted/40 px-3 py-2">
            <div><b>{result.segurados}</b> segurado(s) · <b>{result.incluidos}</b> competência(s) incluída(s) · <b>{result.atualizados}</b> atualizada(s)
              {result.cpfs_nao_cadastrados > 0 && <> · <span className="text-warning">{result.cpfs_nao_cadastrados} CPF(s) não cadastrado(s)</span></>}</div>
            {result.erros.length > 0 && (
              <ul className="mt-1 max-h-40 list-disc overflow-auto pl-5 text-warning">
                {result.erros.map((e, i) => <li key={i}>Linha {e.linha}: {e.mensagem}</li>)}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}