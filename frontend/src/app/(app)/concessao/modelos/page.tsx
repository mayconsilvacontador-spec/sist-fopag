"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Plus } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, type Paginated } from "@/lib/api";

type Tpl = { id?: string; kind: string; kind_display?: string; concession_kind: string; concession_kind_display?: string; title: string; body: string; signer?: string; active?: boolean };

const KINDS = [
  { value: "PORTARIA", label: "Portaria (a minuta usa o mesmo texto)" },
  { value: "CIENCIA_INDEFERIMENTO", label: "Ofício de ciência de indeferimento" },
  { value: "PORTARIA_ANULACAO", label: "Portaria de anulação (a minuta usa o mesmo texto)" },
  { value: "TERMO_DESISTENCIA", label: "Termo de desistência e arquivamento" },
  { value: "RELATORIO_INSTRUCAO", label: "Relatório de instrução (Benefícios)" },
  { value: "PARECER_JURIDICO", label: "Parecer jurídico" },
  { value: "PARECER_CONTROLE", label: "Análise de conformidade (Controle Interno)" },
];
const CKINDS = [
  { value: "", label: "Todos os tipos" }, { value: "APOSENTADORIA", label: "Aposentadoria" },
  { value: "PENSAO", label: "Pensão por morte" }, { value: "REVISAO", label: "Revisão" },
];
const MARKERS = [
  "instituicao", "instituicao_maiusculo", "sigla", "processo", "numero_portaria", "data_portaria", "data_portaria_extenso",
  "nome", "cpf", "matricula", "cargo", "orgao", "modalidade", "modalidade_maiusculo", "regra", "fundamento",
  "fundamento_local", "data_validade", "valor", "valor_extenso", "forma_proventos", "paridade", "instituidor",
  "cpf_instituidor", "data_obito", "cotas", "beneficio_revisto", "valor_anterior", "motivo_revisao",
  "motivo_indeferimento", "tce_processo", "portaria_original", "reimplantacao", "hoje_extenso",
];

export default function Page() {
  return <RequirePermission module="concessao.modelos"><Templates /></RequirePermission>;
}

function Templates() {
  const { can } = useSession();
  const { data, mutate } = useSWR<Paginated<Tpl>>("concessao-modelos?page_size=100", fetcher);
  const defaults = useSWR<Tpl[]>("concessao-modelos/defaults", fetcher);
  const [editing, setEditing] = useState<Tpl | null>(null);
  const fields: FieldDef[] = [
    { name: "kind", label: "Documento", type: "select", required: true, options: KINDS },
    { name: "concession_kind", label: "Tipo de concessão", type: "select", options: CKINDS.slice(1) },
    { name: "title", label: "Título (cabeçalho)", required: true, wide: true },
    { name: "body", label: "Texto — um parágrafo por linha", type: "textarea", required: true },
    { name: "signer", label: "Assinatura (nome e cargo)", wide: true },
    ...(editing?.id ? [{ name: "active", label: "Ativo", type: "checkbox" as const }] : []),
  ];
  const fromDefault = (kind: string, ck: string) => {
    const d = defaults.data?.find((x) => x.kind === kind && x.concession_kind === ck) ?? defaults.data?.find((x) => x.kind === kind && !x.concession_kind);
    setEditing({ kind, concession_kind: ck, title: d?.title ?? "", body: d?.body ?? "", signer: "Presidente do {sigla}" });
  };
  return (
    <>
      <PageHeader title="Modelos de portaria e ofício" breadcrumb={[{ label: "Concessão de Benefícios" }, { label: "Modelos" }]}
        description="Texto usado pelo sistema para gerar a minuta, a portaria, o ofício de indeferimento e a anulação. Sem modelo próprio, vale o texto padrão (redação sugerida — ajuste com a Procuradoria Jurídica)."
        actions={can("concessao.modelos", "incluir") && <Button onClick={() => fromDefault("PORTARIA", "APOSENTADORIA")}><Plus /> Novo modelo (a partir do padrão)</Button>} />
      <Card className="mb-3 px-4 py-3 text-xs">
        <div className="mb-1 font-medium">Marcadores disponíveis (escreva entre chaves, ex.: {"{nome}"})</div>
        <div className="flex flex-wrap gap-1">{MARKERS.map((m) => <code key={m} className="rounded bg-muted px-1.5 py-0.5">{`{${m}}`}</code>)}</div>
      </Card>
      <Card>
        <Table>
          <TableHeader><TableRow><TableHead>Documento</TableHead><TableHead>Tipo</TableHead><TableHead>Título</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={5} />}
            {data?.results.map((t) => (
              <TableRow key={t.id}>
                <TableCell>{t.kind_display}</TableCell><TableCell>{t.concession_kind_display || "Todos"}</TableCell>
                <TableCell className="text-xs">{t.title}</TableCell>
                <TableCell>{t.active ? <Badge variant="success">Ativo</Badge> : <Badge variant="neutral">Inativo</Badge>}</TableCell>
                <TableCell>{can("concessao.modelos", "editar") && <Button size="sm" variant="ghost" onClick={() => setEditing(t)}>Editar</Button>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum modelo próprio: o sistema usa os textos padrão." />}
          </TableBody>
        </Table>
      </Card>
      {editing && (
        <FormDialog title={editing.id ? "Editar modelo" : "Novo modelo"} size="lg" fields={fields} initial={{ ...editing }}
          description="Alterações valem para os próximos documentos gerados; os já gerados ficam guardados como foram emitidos."
          onClose={() => setEditing(null)}
          submit={async (body) => {
            if (editing.id) await api(`concessao-modelos/${editing.id}`, { method: "PATCH", body });
            else await api("concessao-modelos", { method: "POST", body });
            toast.success("Modelo salvo.");
            mutate();
          }} />
      )}
    </>
  );
}
