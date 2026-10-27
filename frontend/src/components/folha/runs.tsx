"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCurrency, formatInt } from "@/lib/format";
import type { PayrollRun, RunStatus } from "@/lib/types";

export const RUN_VARIANT: Record<RunStatus, "default" | "info" | "success" | "warning" | "neutral"> = {
  ABERTA: "neutral", CALCULADA: "info", CONFERIDA: "warning", FECHADA: "default", PAGA: "success",
};

const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

type Props = {
  module: string;
  title: string;
  description: string;
  /** situações exibidas (vazio = todas) */
  statuses?: RunStatus[];
  kind?: "MENSAL" | "DECIMO";
  /** permite abrir folha nesta tela */
  canOpen?: boolean;
  /** aba aberta ao clicar na folha */
  tab?: string;
};

export function RunsPage(props: Props) {
  return (
    <RequirePermission module={props.module}>
      <Runs {...props} />
    </RequirePermission>
  );
}

function Runs({ title, description, statuses, kind, canOpen, tab }: Props) {
  const router = useRouter();
  const { can } = useSession();
  const [status, setStatus] = useState("");
  const [massa, setMassa] = useState("");
  const [page, setPage] = useState(1);
  const [opening, setOpening] = useState(false);
  const [removing, setRemoving] = useState<PayrollRun | null>(null);
  const { data, error, isLoading, mutate } = useSWR<Paginated<PayrollRun>>(
    `folha/folhas${qs({ status, situacoes: status ? undefined : statuses?.join(","), kind, massa, page })}`, fetcher,
    { keepPreviousData: true });
  // A API devolve a lista simples (sem paginação)
  const groups = useSWR<{ id: string; code: string; name: string; active: boolean }[]>("payroll-groups", fetcher);
  const rows = data?.results;
  const allowOpen = canOpen && (kind === "DECIMO" ? can("folha.decimo_terceiro", "calcular") : can("folha.folha_mensal", "incluir"));
  const allowDelete = can("folha.folha_mensal", "excluir");
  const cols = allowDelete ? 9 : 8;
  const now = new Date();

  return (
    <>
      <PageHeader title={title} description={description} breadcrumb={[{ label: "Folha de Benefícios" }, { label: title }]}
        actions={allowOpen && <Button onClick={() => setOpening(true)}><Plus /> Abrir folha</Button>} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <Select className="w-44" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
            <option value="">{statuses?.length ? "Situações desta etapa" : "Todas as situações"}</option>
            {(Object.keys(RUN_VARIANT) as RunStatus[]).map((s) => <option key={s} value={s}>{s.charAt(0) + s.slice(1).toLowerCase()}</option>)}
          </Select>
          <Select className="w-48" value={massa} onChange={(e) => { setMassa(e.target.value); setPage(1); }} aria-label="Folha">
            <option value="">Todas as folhas</option><option value="FINANCEIRO">Financeiro</option><option value="PREVIDENCIARIO">Previdenciário</option><option value="COMPRA_VIDAS">Compra de Vidas</option>
          </Select>
          {statuses?.length ? <span className="text-2xs text-muted-foreground">Mostrando: {statuses.map((s) => s.toLowerCase()).join(", ")}</span> : null}
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Competência</TableHead><TableHead>Folha</TableHead><TableHead>Tipo</TableHead><TableHead className="text-right">Benefícios</TableHead><TableHead className="text-right">Proventos</TableHead><TableHead className="text-right">Descontos</TableHead><TableHead className="text-right">Líquido</TableHead><TableHead>Situação</TableHead>{allowDelete && <TableHead className="w-10" />}</TableRow></TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={cols} />}
            {rows?.map((r) => (
              <TableRow key={r.id} className="cursor-pointer" onClick={() => router.push(`/folha/folha-mensal/${r.id}${tab ? `?aba=${tab}` : ""}`)}>
                <TableCell className="font-medium text-primary">{MONTHS[r.month - 1]}/{r.year}</TableCell>
                <TableCell><Badge variant={r.folha === "FIN" ? "info" : "default"}>{r.folha}</Badge> <span className="text-2xs text-muted-foreground">{r.folha_name}</span></TableCell>
                <TableCell>{r.kind_display}</TableCell>
                <TableCell className="text-right tabular">{formatInt(r.totals.beneficiarios ?? 0)}</TableCell>
                <TableCell className="text-right tabular">{r.totals.proventos ? formatCurrency(r.totals.proventos) : "—"}</TableCell>
                <TableCell className="text-right tabular">{r.totals.descontos ? formatCurrency(r.totals.descontos) : "—"}</TableCell>
                <TableCell className="text-right tabular font-medium">{r.totals.liquido ? formatCurrency(r.totals.liquido) : "—"}</TableCell>
                <TableCell><Badge variant={RUN_VARIANT[r.status]}>{r.status_display}</Badge></TableCell>
                {allowDelete && (
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" title="Excluir folha" aria-label={`Excluir folha ${MONTHS[r.month - 1]}/${r.year} ${r.folha}`}
                      onClick={(e) => { e.stopPropagation(); setRemoving(r); }}>
                      <Trash2 className="text-destructive" />
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {rows?.length === 0 && <EmptyRow cols={cols} text="Nenhuma folha nesta etapa." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {opening && (
        <FormDialog title={kind === "DECIMO" ? "Abrir folha de 13º" : "Abrir folha"} size="sm"
          description="Uma folha por competência e por massa (Financeiro, Previdenciário, Compra de Vidas)."
          initial={{ year: now.getFullYear(), month: kind === "DECIMO" ? 12 : now.getMonth() + 1, kind: kind ?? "MENSAL" }}
          fields={[
            { name: "payroll_group", label: "Folha (massa)", type: "select", required: true, wide: true,
              options: (groups.data ?? []).filter((g) => g.active).map((g) => ({ value: g.id, label: `${g.code} — ${g.name}` })) },
            { name: "month", label: "Mês", type: "select", required: true, options: MONTHS.map((m, i) => ({ value: i + 1, label: m })) },
            { name: "year", label: "Ano", type: "number", required: true },
            ...(kind ? [] : [{ name: "kind", label: "Tipo", type: "select" as const, required: true, options: [{ value: "MENSAL", label: "Mensal" }, { value: "DECIMO", label: "13º (gratificação natalina)" }] }]),
          ]}
          submitLabel="Abrir"
          onClose={() => setOpening(false)}
          submit={async (body) => {
            const run = await api<PayrollRun>("folha/folhas", { method: "POST", body: { ...body, kind: kind ?? body.kind } });
            toast.success("Folha aberta. Agora calcule.");
            mutate();
            router.push(`/folha/folha-mensal/${run.id}`);
          }} />
      )}
      {removing && (
        <FormDialog title="Excluir folha" size="sm"
          description={`${MONTHS[removing.month - 1]}/${removing.year} — ${removing.folha} (${removing.status_display.toLowerCase()}). Use só para folha aberta por engano. Só a folha mais recente de cada massa pode ser excluída; folha paga com beneficiários, com lote de pagamento ou com eventos do eSocial não pode. A exclusão fica registrada na auditoria.`}
          initial={{ justification: "", password: "" }}
          fields={[
            { name: "justification", label: "Motivo da exclusão", type: "textarea", required: true, wide: true },
            { name: "password", label: "Sua senha (assinatura eletrônica)", type: "password", required: true, wide: true },
          ]}
          submitLabel="Excluir folha"
          onClose={() => setRemoving(null)}
          submit={async (body) => {
            await api(`folha/folhas/${removing.id}/excluir`, { method: "POST", body });
            toast.success("Folha excluída.");
            mutate();
          }} />
      )}
    </>
  );
}
