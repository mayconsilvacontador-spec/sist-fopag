"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { Rocket, Search } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCPF, formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import type { BenefitEventRow, BenefitRow } from "@/lib/types";

type Op = "SUSPENSAO" | "RESTABELECIMENTO" | "CESSACAO" | "REVERSAO";
const OPS: Record<Op, { label: string; module: string; when: BenefitRow["status"][]; hint: string }> = {
  SUSPENSAO: { label: "Suspensão", module: "concessao.suspensao", when: ["ATIVO"], hint: "Ex.: prova de vida não realizada, recadastramento pendente." },
  RESTABELECIMENTO: { label: "Restabelecimento", module: "concessao.suspensao", when: ["SUSPENSO"], hint: "Volta a pagar o benefício suspenso." },
  CESSACAO: { label: "Cessação", module: "concessao.cessacao", when: ["ATIVO", "SUSPENSO"], hint: "Ex.: óbito, fim da cota temporária (21 anos), perda da qualidade de dependente." },
  REVERSAO: { label: "Reversão", module: "concessao.reversao", when: ["ATIVO", "SUSPENSO"], hint: "Retorno do aposentado à atividade. Cadastre o novo vínculo na Pasta do Servidor." },
};
const STATUS_VARIANT = { ATIVO: "success", SUSPENSO: "warning", CESSADO: "neutral" } as const;

export function BenefitsScreen({ focus, area }: { focus?: Op; area?: "concessao" }) {
  return (
    <RequirePermission module="folha.beneficiarios">
      <Screen focus={focus} area={area} />
    </RequirePermission>
  );
}

function Screen({ focus, area }: { focus?: Op; area?: "concessao" }) {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("ATIVO");
  const [massa, setMassa] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<BenefitRow | null>(null);
  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id");
    if (id) api<BenefitRow>(`beneficios/${id}`).then(setSelected).catch(() => undefined);
  }, []);
  const { data, error, isLoading, mutate } = useSWR<Paginated<BenefitRow>>(
    `beneficios${qs({ search: debounced, kind, status, massa, page })}`, fetcher, { keepPreviousData: true });
  // area "concessao": todas as operações (suspender, restabelecer, cessar, reverter) numa tela só
  const ops = Boolean(focus || area);
  const title = focus ? OPS[focus].label + " de benefícios" : area ? "Suspender, cessar ou reverter" : "Beneficiários";

  return (
    <>
      <PageHeader title={title}
        description={focus ? `${OPS[focus].hint} Escolha o benefício na lista.`
          : area ? "Clique no benefício para suspender (ou restabelecer), cessar (óbito, fim da cota) ou reverter (retorno à atividade). Cada operação pede a sua senha e fica registrada."
            : "Aposentadorias e pensões implantadas — base da folha de benefícios."}
        breadcrumb={[{ label: ops ? "Concessão de Benefícios" : "Folha de Benefícios" }, { label: title }]} />
      <Tabs defaultValue="implantados">
        {!ops && (
          <TabsList className="mb-3">
            <TabsTrigger value="implantados">Benefícios implantados</TabsTrigger>
            <TabsTrigger value="importados">Importados aguardando implantação</TabsTrigger>
          </TabsList>
        )}
        <TabsContent value="implantados" className="pt-0">
          <Card>
            <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
              <div className="relative w-full max-w-sm">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Beneficiário, instituidor, CPF ou matrícula" className="pl-8" />
              </div>
              <Select className="w-40" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} aria-label="Tipo">
                <option value="">Todos os tipos</option><option value="APOSENTADORIA">Aposentadorias</option><option value="PENSAO">Pensões</option>
              </Select>
              <Select className="w-36" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
                <option value="ATIVO">Ativos</option><option value="SUSPENSO">Suspensos</option><option value="CESSADO">Cessados</option><option value="">Todos</option>
              </Select>
              <Select className="w-48" value={massa} onChange={(e) => { setMassa(e.target.value); setPage(1); }} aria-label="Folha">
                <option value="">Todas as folhas</option><option value="FINANCEIRO">Financeiro</option><option value="PREVIDENCIARIO">Previdenciário</option><option value="COMPRA_VIDAS">Compra de Vidas</option>
              </Select>
            </div>
            {error && <div className="p-4"><ErrorState error={error} /></div>}
            <Table>
              <TableHeader><TableRow><TableHead>Beneficiário</TableHead><TableHead>Benefício</TableHead><TableHead>Folha</TableHead><TableHead>Início</TableHead><TableHead className="text-right">Valor</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
              <TableBody>
                {isLoading && !data && <LoadingRows cols={6} />}
                {data?.results.map((b) => (
                  <TableRow key={b.id} className="cursor-pointer" onClick={() => setSelected(b)}>
                    <TableCell><div className="font-medium text-primary">{b.beneficiary_name || "Nome não informado"}</div><div className="text-2xs text-muted-foreground">{b.beneficiary_cpf}{b.instituidor_name ? ` · instituidor: ${b.instituidor_name}` : ""}</div></TableCell>
                    <TableCell className="text-xs">{b.kind_display}{b.modality_display ? ` — ${b.modality_display}` : ""}{b.percent ? ` · cota ${Number(b.percent).toLocaleString("pt-BR")}%` : ""}{b.imported && <Badge variant="neutral" className="ml-1">Importado</Badge>}</TableCell>
                    <TableCell><Badge variant={b.folha === "FIN" ? "info" : "default"}>{b.folha}</Badge></TableCell>
                    <TableCell>{formatDate(b.start_date)}{b.end_date && <div className="text-2xs text-muted-foreground">até {formatDate(b.end_date)}</div>}</TableCell>
                    <TableCell className="text-right tabular">{formatCurrency(b.amount)}</TableCell>
                    <TableCell><Badge variant={STATUS_VARIANT[b.status]}>{b.status_display}</Badge></TableCell>
                  </TableRow>
                ))}
                {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum benefício." />}
              </TableBody>
            </Table>
            {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
          </Card>
        </TabsContent>
        <TabsContent value="importados" className="pt-0"><Legacy canImplant={can("folha.beneficiarios", "incluir")} onDone={() => mutate()} /></TabsContent>
      </Tabs>
      {selected && <BenefitDialog b={selected} focus={focus} onClose={() => setSelected(null)} onChanged={(nb) => { setSelected(nb); mutate(); }} />}
    </>
  );
}

function BenefitDialog({ b, focus, onClose, onChanged }: { b: BenefitRow; focus?: Op; onClose: () => void; onChanged: (b: BenefitRow) => void }) {
  const { can } = useSession();
  const events = useSWR<BenefitEventRow[]>(`beneficios/${b.id}/events`, fetcher);
  const [op, setOp] = useState<Op | null>(null);
  const [esocial, setEsocial] = useState(false);
  const ops = (Object.keys(OPS) as Op[]).filter((k) => OPS[k].when.includes(b.status) && can(OPS[k].module, "incluir") && (!focus || k === focus || (focus === "SUSPENSAO" && k === "RESTABELECIMENTO")));
  const fields: FieldDef[] = [
    { name: "date", label: "Data de efeito", type: "date", required: true },
    { name: "act", label: "Ato / documento", hint: "Portaria, decisão judicial, despacho..." },
    { name: "justification", label: "Justificativa / fundamento", type: "textarea", required: true },
    { name: "password", label: "Sua senha (assinatura eletrônica)", type: "password", required: true, wide: true },
  ];

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{b.kind_display} — {b.beneficiary_name || formatCPF(b.beneficiary_cpf)}</DialogTitle>
          <DialogDescription>
            {b.modality_display ?? ""} · Folha {b.folha_name} · {formatCurrency(b.amount)} · <Badge variant={STATUS_VARIANT[b.status]}>{b.status_display}</Badge>
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3 text-xs">
          <div className="grid gap-1 sm:grid-cols-2">
            <div><span className="text-muted-foreground">Início: </span>{formatDate(b.start_date)}{b.end_date ? ` · fim ${formatDate(b.end_date)}` : ""}</div>
            <div><span className="text-muted-foreground">Integralidade / paridade: </span>{b.integralidade ? "Sim" : "Não"} / {b.paridade ? "Sim" : "Não"}</div>
            <div className="sm:col-span-2"><span className="text-muted-foreground">Fundamentação: </span>{b.legal_basis}</div>
            {b.instituidor_name && <div><span className="text-muted-foreground">Instituidor: </span>{b.instituidor_name}</div>}
            {b.concession && <div><span className="text-muted-foreground">Concessão: </span><Link className="text-primary hover:underline" href={`/concessao/processo/${b.concession}`}>processo {b.concession_process}</Link></div>}
          </div>
          {ops.length > 0 && <div className="flex flex-wrap gap-2">{ops.map((k) => <Button key={k} size="sm" variant="outline" onClick={() => setOp(k)}>{OPS[k].label}</Button>)}</div>}
          <div className="rounded border px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <div>
                <span className="section-label">eSocial</span>{" "}
                <span className="text-muted-foreground">nº {b.esocial_nr || "(gerado no S-2410)"} · tipo (Tabela 25): <b>{b.esocial_tp_beneficio || "não informado"}</b>
                  {b.status === "CESSADO" && <> · motivo do término (Tabela 26): <b>{b.esocial_mtv_termino || "não informado"}</b></>}</span>
              </div>
              {can("folha.beneficiarios", "editar") && <Button size="sm" variant="outline" onClick={() => setEsocial(true)}>Informar códigos</Button>}
            </div>
          </div>
          <div>
            <div className="section-label mb-1">Histórico</div>
            <ol className="space-y-1.5">
              {events.data?.map((e) => (
                <li key={e.id} className="rounded border px-3 py-1.5">
                  <div><b>{e.kind_display}</b> — efeito em {formatDate(e.date)} <span className="text-2xs text-muted-foreground">({formatDateTime(e.created_at)} · {e.user_name || "Sistema"})</span></div>
                  <div>{e.justification}</div>
                  {e.old_values.valor && e.new_values.valor && e.old_values.valor !== e.new_values.valor && (
                    <div className="text-2xs">Valor: {formatCurrency(e.old_values.valor)} → {formatCurrency(e.new_values.valor)}</div>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </DialogBody>
      </DialogContent>
      {op && (
        <FormDialog title={OPS[op].label} description={OPS[op].hint} fields={fields} submitLabel={`Registrar ${OPS[op].label.toLowerCase()}`}
          initial={{ date: new Date().toISOString().slice(0, 10) }} onClose={() => setOp(null)}
          submit={async (body) => {
            const nb = await api<BenefitRow>(`beneficios/${b.id}/event`, { method: "POST", body: { ...body, kind: op } });
            toast.success("Registrado no histórico do benefício.");
            events.mutate();
            onChanged(nb);
          }} />
      )}
      {esocial && (
        <FormDialog title="Códigos do eSocial" size="sm" onClose={() => setEsocial(false)}
          description="Usados nos eventos S-2410 (início) e S-2420 (término). Consulte as Tabelas 25 e 26 do leiaute do eSocial vigente."
          fields={[
            { name: "esocial_tp_beneficio", label: "Tipo de benefício (Tabela 25)", type: "digits", maxLength: 4, wide: true, hint: "4 dígitos" },
            { name: "esocial_mtv_termino", label: "Motivo do término (Tabela 26)", type: "digits", maxLength: 2, wide: true, hint: "2 dígitos — só para benefício cessado" },
          ]}
          initial={{ esocial_tp_beneficio: b.esocial_tp_beneficio, esocial_mtv_termino: b.esocial_mtv_termino }}
          submit={async (body) => {
            const nb = await api<BenefitRow>(`beneficios/${b.id}/esocial`, { method: "POST", body });
            toast.success("Códigos salvos. Revalide os eventos pendentes em eSocial › Pendências.");
            onChanged(nb);
          }} />
      )}
    </Dialog>
  );
}

type LegacyRow = { id: string; kind: string; beneficiary_name: string; beneficiary_cpf: string; instituidor_name: string; segment: string; start_date: string | null; amount: string | null; registration: string };

function Legacy({ canImplant, onDone }: { canImplant: boolean; onDone: () => void }) {
  const [page, setPage] = useState(1);
  const { data, mutate } = useSWR<Paginated<LegacyRow>>(`beneficios-importados${qs({ page })}`, fetcher);
  const [confirming, setConfirming] = useState(false);
  const all = async (password: string) => {
    const r = await api<{ implantados: number; erros: { beneficiario: string; erro: string }[] }>("beneficios-importados/implant-all", { method: "POST", body: { password } });
    toast.success(`${r.implantados} benefício(s) implantado(s)${r.erros.length ? `; ${r.erros.length} com pendência` : ""}.`);
    mutate();
    onDone();
  };
  return (
    <Card>
      <div className="flex items-center justify-between border-b px-4 py-2.5 text-xs">
        <span className="text-muted-foreground">Aposentadorias e pensões trazidas pela importação (base SPREV). Ao implantar, entram na folha com o valor e a data de início do sistema anterior.</span>
        {canImplant && !!data?.count && <Button size="sm" onClick={() => setConfirming(true)}><Rocket /> Implantar todos ({data.count})</Button>}
        {confirming && (<FormDialog title={`Implantar ${data?.count ?? 0} benefício(s) importado(s)`} size="sm" onClose={() => setConfirming(false)}
          description="São benefícios já concedidos no sistema anterior (base SPREV). Entram na folha com o valor e o início de origem. A operação é registrada e não pode ser desfeita (só por cessação)."
          fields={[{ name: "password", label: "Sua senha (assinatura eletrônica)", type: "password", required: true, wide: true }]}
          submitLabel="Implantar" submit={async (b) => all(String(b.password))} />)}
      </div>
      <Table>
        <TableHeader><TableRow><TableHead>Beneficiário</TableHead><TableHead>Tipo</TableHead><TableHead>Massa</TableHead><TableHead>Início</TableHead><TableHead className="text-right">Valor</TableHead></TableRow></TableHeader>
        <TableBody>
          {data?.results.map((x) => (
            <TableRow key={x.id}>
              <TableCell><div className="font-medium">{x.beneficiary_name || "Nome não informado"}</div><div className="text-2xs text-muted-foreground">{formatCPF(x.beneficiary_cpf)}{x.instituidor_name ? ` · instituidor: ${x.instituidor_name}` : ""}</div></TableCell>
              <TableCell>{x.kind === "PENSAO" ? "Pensão" : "Aposentadoria"}</TableCell>
              <TableCell>{x.segment}</TableCell>
              <TableCell>{formatDate(x.start_date)}</TableCell>
              <TableCell className="text-right tabular">{x.amount ? formatCurrency(x.amount) : <span className="text-warning">sem valor</span>}</TableCell>
            </TableRow>
          ))}
          {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum benefício importado aguardando implantação." />}
        </TableBody>
      </Table>
      {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
    </Card>
  );
}
