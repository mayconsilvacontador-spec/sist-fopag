"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { GitBranch, Pencil, Plus, Search } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox, Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Rubric } from "@/lib/types";

const CALC_OPTIONS = [
  ["APOSENTADORIA", "Proventos de aposentadoria"], ["PENSAO", "Pensão por morte"], ["RETROATIVO", "Retroativo do benefício"],
  ["DECIMO", "13º (gratificação natalina)"], ["CONTRIB_RPPS", "Contribuição ao RPPS"], ["CONTRIB_13", "Contribuição s/ 13º"],
  ["IRRF", "IRRF"], ["IRRF_13", "IRRF s/ 13º"], ["IRRF_RRA", "IRRF s/ rendimentos acumulados (RRA)"],
  ["PENSAO_ALIMENTICIA", "Pensão alimentícia"], ["PENSAO_ALIMENTICIA_13", "Pensão alimentícia s/ 13º"],
  ["CONSIGNACAO", "Consignação"], ["MANUAL", "Lançamento (valor informado)"],
].map(([value, label]) => ({ value, label }));

const FLAGS: FieldDef[] = [
  { name: "inc_ir", label: "Incide IRRF", type: "checkbox" },
  { name: "inc_rpps", label: "Incide contribuição RPPS", type: "checkbox" },
  { name: "inc_13", label: "Integra o 13º", type: "checkbox" },
  { name: "inc_margem", label: "Integra a base da margem consignável", type: "checkbox" },
  { name: "ir_deduction", label: "Dedutível do IRRF", type: "checkbox" },
];

export function RubricsPage() {
  return (
    <RequirePermission module="folha.rubricas">
      <Rubrics />
    </RequirePermission>
  );
}

function Rubrics() {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [current, setCurrent] = useState(true);
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<{ mode: "new" | "edit" | "version"; r?: Rubric } | null>(null);
  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Rubric>>(
    `folha/rubricas${qs({ search: debounced, vigentes: current ? 1 : undefined, page, page_size: 50 })}`, fetcher, { keepPreviousData: true });

  const fields = (mode: "new" | "edit" | "version"): FieldDef[] => [
    ...(mode === "new" ? [{ name: "code", label: "Código", required: true, maxLength: 6 } as FieldDef] : []),
    { name: "name", label: "Descrição", required: true, maxLength: 80, wide: mode !== "new" },
    ...(mode !== "version" ? [
      { name: "kind", label: "Tipo", type: "select", required: true, options: [{ value: "PROVENTO", label: "Provento" }, { value: "DESCONTO", label: "Desconto" }, { value: "INFORMATIVA", label: "Informativa" }] } as FieldDef,
      { name: "calc", label: "Forma de cálculo", type: "select", required: true, options: CALC_OPTIONS } as FieldDef,
    ] : []),
    ...FLAGS,
    { name: "esocial_nature", label: "Natureza (eSocial, Tabela 03)", type: "digits", maxLength: 4, hint: "4 dígitos — obrigatório no S-1010" },
    { name: "esocial_inc_irrf", label: "Incidência IRRF (codIncIRRF)", type: "digits", maxLength: 4 },
    { name: "esocial_inc_cprp", label: "Incidência RPPS (codIncCPRP)", type: "digits", maxLength: 2 },
    { name: "esocial_inc_cp", label: "Incidência CP/RGPS (codIncCP)", type: "digits", maxLength: 2, hint: "Benefícios do RPPS: normalmente 00" },
    ...(mode === "new" ? [{ name: "valid_from", label: "Vigência inicial", type: "date", required: true } as FieldDef] : []),
    ...(mode === "version" ? [
      { name: "valid_from", label: "Nova versão vale a partir de", type: "date", required: true } as FieldDef,
      { name: "reason", label: "Motivo da nova versão", type: "textarea", required: true } as FieldDef,
    ] : []),
  ];

  return (
    <>
      <PageHeader title="Rubricas" breadcrumb={[{ label: "Folha de Benefícios" }, { label: "Rubricas" }]}
        description="Proventos e descontos da folha. Rubrica já usada em folha não é alterada: cria-se nova VERSÃO com vigência, e cada contracheque guarda a versão usada."
        actions={can("folha.rubricas", "incluir") && <Button onClick={() => setDialog({ mode: "new" })}><Plus /> Nova rubrica</Button>} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="relative w-full max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Código ou descrição" className="pl-8" />
          </div>
          <label className="flex items-center gap-2 text-xs"><Checkbox checked={current} onChange={(e) => { setCurrent(e.target.checked); setPage(1); }} /> Somente versões vigentes</label>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Código</TableHead><TableHead>Descrição</TableHead><TableHead>Tipo</TableHead><TableHead>Cálculo</TableHead><TableHead>Incidências</TableHead><TableHead>Vigência</TableHead><TableHead className="w-20" /></TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={7} />}
            {data?.results.map((r) => (
              <TableRow key={r.id} className={r.active ? "" : "opacity-60"}>
                <TableCell className="font-mono text-xs">{r.code} <span className="text-2xs text-muted-foreground">v{r.version}</span></TableCell>
                <TableCell>{r.name}{!r.active && <Badge variant="neutral" className="ml-1">Inativa</Badge>}</TableCell>
                <TableCell><Badge variant={r.kind === "PROVENTO" ? "success" : r.kind === "DESCONTO" ? "neutral" : "info"}>{r.kind_display}</Badge></TableCell>
                <TableCell className="text-xs">{r.calc_display}</TableCell>
                <TableCell className="text-2xs">{[r.inc_ir && "IR", r.inc_rpps && "RPPS", r.inc_13 && "13º", r.inc_margem && "margem", r.ir_deduction && "deduz IR"].filter(Boolean).join(" · ") || "—"}</TableCell>
                <TableCell className="text-xs">{formatDate(r.valid_from)}{r.valid_to ? ` a ${formatDate(r.valid_to)}` : " em diante"}</TableCell>
                <TableCell className="flex gap-1">
                  {can("folha.rubricas", "editar") && !r.valid_to && <>
                    <Button variant="ghost" size="icon" className="h-7 w-7" title="Editar (só se ainda não usada; ativar/inativar sempre)" onClick={() => setDialog({ mode: "edit", r })}><Pencil /></Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" title="Nova versão" onClick={() => setDialog({ mode: "version", r })}><GitBranch /></Button>
                  </>}
                </TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={7} text="Nenhuma rubrica. Rode 'seed_payroll' para carregar as rubricas padrão." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {dialog && (
        <FormDialog size="md"
          title={dialog.mode === "new" ? "Nova rubrica" : dialog.mode === "edit" ? `Editar rubrica ${dialog.r!.code}` : `Nova versão da rubrica ${dialog.r!.code}`}
          description={dialog.mode === "version" ? "A versão atual é encerrada na véspera; folhas já calculadas continuam com a versão antiga." : undefined}
          fields={[...fields(dialog.mode), ...(dialog.mode === "edit" ? [{ name: "active", label: "Ativa", type: "checkbox" } as FieldDef] : [])]}
          initial={dialog.r ? { ...dialog.r, valid_from: dialog.mode === "version" ? "" : dialog.r.valid_from } : { kind: "PROVENTO", calc: "MANUAL", valid_from: new Date().toISOString().slice(0, 10) }}
          onClose={() => setDialog(null)}
          submit={async (body) => {
            if (dialog.mode === "new") await api("folha/rubricas", { method: "POST", body });
            else if (dialog.mode === "edit") await api(`folha/rubricas/${dialog.r!.id}`, { method: "PATCH", body });
            else await api(`folha/rubricas/${dialog.r!.id}/version`, { method: "POST", body });
            toast.success("Rubrica salva.");
            mutate();
          }} />
      )}
    </>
  );
}
