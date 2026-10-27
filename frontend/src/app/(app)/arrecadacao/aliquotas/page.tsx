"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2, Plus } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher } from "@/lib/api";
import { formatDate } from "@/lib/format";

type Vig = { inicio: string; fim: string | null; percentual: string; fundamento: string; motivo: string; versao: number };
type Grupo = { tipo: "SERVIDOR" | "PATRONAL"; chave: string; descricao: string; vigencias: Vig[] };

export default function AliquotasPage() {
  return (
    <RequirePermission module="arrecadacao.aliquotas">
      <Aliquotas />
    </RequirePermission>
  );
}

function Aliquotas() {
  const { can } = useSession();
  const { data, mutate } = useSWR<Grupo[]>("arrecadacao/aliquotas", fetcher);
  const [f, setF] = useState({ tipo: "SERVIDOR", percentual: "", inicio: "", fundamento: "", motivo: "" });
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((x) => ({ ...x, [k]: e.target.value }));

  const save = async () => {
    if (!f.percentual || !f.inicio || !f.fundamento) { toast.error("Informe alíquota, início e fundamento legal."); return; }
    setBusy(true);
    try {
      const [y, m] = f.inicio.split("-");
      await mutate(await api<Grupo[]>("arrecadacao/aliquotas", { method: "POST", body: { ...f, inicio: `${m}/${y}` } }), false);
      toast.success("Vigência cadastrada.");
      setF((x) => ({ ...x, percentual: "", inicio: "", fundamento: "", motivo: "" }));
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Alíquotas de contribuição"
        description="Alíquotas do servidor e patronal com vigência. São usadas na folha, na arrecadação e no controle da contribuição de cada servidor."
        breadcrumb={[{ label: "Arrecadação" }, { label: "Alíquotas" }]} />
      {can("arrecadacao.aliquotas", "incluir") && (
        <Card className="mb-4">
          <CardContent className="p-4">
            <h2 className="mb-3 text-sm font-bold text-primary-strong">Nova vigência</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
              <FormField label="Contribuição" htmlFor="al-tipo">
                <Select id="al-tipo" value={f.tipo} onChange={set("tipo")}>
                  <option value="SERVIDOR">Do servidor</option><option value="PATRONAL">Patronal</option>
                </Select>
              </FormField>
              <FormField label="Alíquota (%)" htmlFor="al-pct"><Input id="al-pct" value={f.percentual} onChange={set("percentual")} placeholder="ex.: 14" /></FormField>
              <FormField label="A partir de" htmlFor="al-ini"><Input id="al-ini" type="month" value={f.inicio} onChange={set("inicio")} /></FormField>
              <FormField label="Fundamento legal" htmlFor="al-fund" className="lg:col-span-2">
                <Input id="al-fund" value={f.fundamento} onChange={set("fundamento")} placeholder="Lei / Emenda / Decreto nº, data" />
              </FormField>
              <div className="flex items-end"><Button onClick={save} disabled={busy} className="w-full">{busy ? <Loader2 className="animate-spin" /> : <Plus />} Cadastrar</Button></div>
              <FormField label="Motivo (para alteração)" htmlFor="al-mot" className="sm:col-span-2 lg:col-span-6">
                <Input id="al-mot" value={f.motivo} onChange={set("motivo")} placeholder="Ex.: reforma da previdência municipal; alíquota anterior a 2025" />
              </FormField>
            </div>
            <p className="mt-2 text-2xs text-muted-foreground">
              Você pode cadastrar uma vigência NOVA (depois da última) ou HISTÓRICA (antes da primeira — por exemplo, 11% até
              08/2025). A vigência anterior é encerrada automaticamente; nada é apagado e tudo fica na auditoria.
            </p>
          </CardContent>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {data?.map((g) => (
          <Card key={g.tipo}>
            <CardContent className="p-4">
              <h2 className="text-sm font-bold text-primary-strong">{g.tipo === "SERVIDOR" ? "Contribuição do servidor" : "Contribuição patronal"}</h2>
              <p className="mb-2 text-xs text-muted-foreground">{g.descricao}</p>
              <Table>
                <TableHeader><TableRow><TableHead>Vigência</TableHead><TableHead className="text-right">Alíquota</TableHead><TableHead>Fundamento</TableHead></TableRow></TableHeader>
                <TableBody>
                  {g.vigencias.map((v) => (
                    <TableRow key={v.versao}>
                      <TableCell className="text-xs">desde {formatDate(v.inicio)}{v.fim ? ` até ${formatDate(v.fim)}` : ""}
                        {!v.fim && <Badge variant="success" className="ml-1">vigente</Badge>}</TableCell>
                      <TableCell className="text-right text-base font-bold text-primary-strong">{v.percentual.replace(".", ",")}%</TableCell>
                      <TableCell className="text-xs">{v.fundamento}{v.motivo && <div className="text-muted-foreground">{v.motivo}</div>}</TableCell>
                    </TableRow>
                  ))}
                  {g.vigencias.length === 0 && (
                    <TableRow><TableCell colSpan={3} className="py-6 text-center text-xs text-muted-foreground">Nenhuma alíquota cadastrada.</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
