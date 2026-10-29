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
import { Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher } from "@/lib/api";

type Tpl = {
  id: string; concession_kind: string; concession_kind_display: string; modality: number | null; modality_display: string | null;
  sector: string; sector_display: string; name: string; help_text: string; source: string; source_display: string;
  system_kind: string; required: boolean; order: number; active: boolean;
};

const KINDS = [{ value: "APOSENTADORIA", label: "Aposentadoria" }, { value: "PENSAO", label: "Pensão por morte" }, { value: "REVISAO", label: "Revisão" }];
const SECTORS = [
  { value: "BENEFICIOS", label: "Benefícios" }, { value: "JURIDICO", label: "Procuradoria Jurídica" },
  { value: "CONTROLE", label: "Controle Interno" }, { value: "PRESIDENCIA", label: "Presidência" }, { value: "FOLHA", label: "Folha de Pagamento" },
];
const MODALITIES = [
  { value: "", label: "Todas as modalidades" }, { value: 1, label: "Por idade" }, { value: 2, label: "Por tempo de contribuição" },
  { value: 3, label: "Compulsória" }, { value: 4, label: "Por incapacidade permanente" }, { value: 5, label: "De professor" },
  { value: 6, label: "Especial — atividade de risco" }, { value: 7, label: "Especial — agentes nocivos" },
];
const SYSTEM_DOCS = [
  { value: "", label: "—" }, { value: "RELATORIO_INSTRUCAO", label: "Relatório de instrução" }, { value: "PARECER_JURIDICO", label: "Parecer jurídico" },
  { value: "PARECER_CONTROLE", label: "Análise de conformidade" }, { value: "PORTARIA", label: "Portaria assinada" },
];
const PERSON_DOCS = [
  { value: "", label: "Não guardar" }, { value: "IDENTIDADE", label: "Identidade (RG/CNH) — permite atualizar o RG" }, { value: "CPF", label: "CPF" },
  { value: "CERT_NASC", label: "Certidão de nascimento" }, { value: "CERT_CASAMENTO", label: "Certidão de casamento / união estável" },
  { value: "CERT_OBITO", label: "Certidão de óbito" }, { value: "RESIDENCIA", label: "Comprovante de residência — permite atualizar o endereço" },
  { value: "CTC", label: "Certidão de Tempo de Contribuição" }, { value: "LAUDO", label: "Laudo médico" }, { value: "ATO", label: "Ato / portaria / decreto" }, { value: "OUTROS", label: "Outros" },
];
const SECTOR_ORDER = Object.fromEntries(SECTORS.map((s, i) => [s.value, i]));

export default function ChecklistTemplatesPage() {
  return (
    <RequirePermission module="concessao.modelos">
      <Templates />
    </RequirePermission>
  );
}

function Templates() {
  const { can } = useSession();
  const [kind, setKind] = useState("APOSENTADORIA");
  const [editing, setEditing] = useState<Tpl | "new" | null>(null);
  const { data, isLoading, mutate } = useSWR<Tpl[]>(`concessao-checklist?concession_kind=${kind}`, fetcher);
  const rows = [...(data ?? [])].sort((a, b) => (SECTOR_ORDER[a.sector] - SECTOR_ORDER[b.sector]) || a.order - b.order);
  const canEdit = can("concessao.modelos", "editar");

  const fields: FieldDef[] = [
    { name: "concession_kind", label: "Tipo de processo", type: "select", required: true, options: KINDS },
    { name: "sector", label: "Setor", type: "select", required: true, options: SECTORS },
    { name: "name", label: "Documento", required: true, wide: true, maxLength: 200 },
    { name: "help_text", label: "Orientação ao setor", wide: true, maxLength: 300 },
    { name: "modality", label: "Só para a modalidade", type: "select", options: MODALITIES, hint: "Só aposentadoria." },
    { name: "source", label: "Origem", type: "select", required: true, options: [{ value: "ANEXO", label: "Anexar documento" }, { value: "SISTEMA", label: "Gerado pelo sistema" }] },
    { name: "system_kind", label: "Documento do sistema", type: "select", options: SYSTEM_DOCS, hint: "Só quando a origem é “gerado pelo sistema”." },
    { name: "person_doc_type", label: "Guardar também no cadastro como", type: "select", options: PERSON_DOCS, hint: "Ao anexar, o arquivo vira uma nova versão nos documentos da pessoa." },
    { name: "order", label: "Ordem", type: "number" },
    { name: "required", label: "Obrigatório (trava a liberação do setor)", type: "checkbox" },
    { name: "active", label: "Ativo", type: "checkbox" },
  ];

  return (
    <>
      <PageHeader title="Checklist de documentos" description="Documentos exigidos por setor no processo digital de concessão. Itens obrigatórios travam a liberação do processo pelo setor."
        breadcrumb={[{ label: "Concessão de Benefícios" }, { label: "Checklist de documentos" }]}
        actions={can("concessao.modelos", "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Documento</Button>} />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5 text-xs">
          <Select className="w-52" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo de processo">
            {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </Select>
          <span className="text-muted-foreground">Lista inicial sugerida a partir dos manuais PREVIBAM (MM-APOSVOL, MM-APOSCOMP, MM-APOSINV, MM-PENSAO, MM-REVEBENEF) — confira e ajuste. Alterações valem para os processos em andamento.</span>
        </div>
        <Table>
          <TableHeader><TableRow><TableHead>Setor</TableHead><TableHead>Documento</TableHead><TableHead>Modalidade</TableHead><TableHead>Origem</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
          <TableBody>
            {isLoading && <LoadingRows cols={5} />}
            {rows.map((r) => (
              <TableRow key={r.id} className={canEdit ? "cursor-pointer" : undefined} onClick={() => canEdit && setEditing(r)}>
                <TableCell>{r.sector_display}</TableCell>
                <TableCell><div className="font-medium">{r.name}</div>{r.help_text && <div className="text-2xs text-muted-foreground">{r.help_text}</div>}</TableCell>
                <TableCell>{r.modality_display || "Todas"}</TableCell>
                <TableCell>{r.source_display}</TableCell>
                <TableCell className="space-x-1">
                  {r.required ? <Badge variant="warning">obrigatório</Badge> : <Badge variant="neutral">opcional</Badge>}
                  {!r.active && <Badge variant="neutral">inativo</Badge>}
                </TableCell>
              </TableRow>
            ))}
            {data && rows.length === 0 && <EmptyRow cols={5} text="Nenhum documento cadastrado para este tipo." />}
          </TableBody>
        </Table>
      </Card>
      {editing && (
        <FormDialog title={editing === "new" ? "Novo documento do checklist" : "Editar documento do checklist"} fields={fields}
          initial={editing === "new" ? { concession_kind: kind, sector: "BENEFICIOS", source: "ANEXO", required: true, active: true, order: 50, modality: "", system_kind: "", person_doc_type: "" }
            : { ...editing, modality: editing.modality ?? "" }}
          onClose={() => setEditing(null)}
          submit={async (body) => {
            const payload = { ...body, modality: body.modality ? Number(body.modality) : null, order: Number(body.order || 0) };
            if (editing === "new") await api("concessao-checklist", { method: "POST", body: payload });
            else await api(`concessao-checklist/${editing.id}`, { method: "PATCH", body: payload });
            toast.success("Checklist atualizado.");
            setEditing(null);
            mutate();
          }} />
      )}
    </>
  );
}
