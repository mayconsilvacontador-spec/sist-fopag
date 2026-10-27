"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, type Paginated } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import {
  ADMISSION_FORM, ELIGIBILITY, EVENT_TYPE, LINK_CLOSE_STATUS, LINK_TYPE, REGIME, SEGMENT, SITUATION,
} from "@/lib/options";
import type { EmploymentLink, FunctionalEventRow } from "@/lib/types";

function linkFields(hasLifePurchase: boolean): FieldDef[] {
  const segments = hasLifePurchase ? SEGMENT : SEGMENT.filter((s) => s.value !== "COMPRA_VIDAS");
  return [
    { name: "organ", label: "Órgão", type: "ref", required: true, wide: true, ref: { endpoint: "organs", label: (r) => String(r.name) } },
    { name: "registration", label: "Matrícula", required: true },
    { name: "link_type", label: "Tipo de vínculo", type: "select", required: true, options: LINK_TYPE },
    { name: "position", label: "Cargo atual", type: "ref", required: true, ref: { endpoint: "positions", label: (r) => String(r.name) } },
    { name: "initial_position", label: "Cargo inicial (se diferente)", type: "ref", ref: { endpoint: "positions", label: (r) => String(r.name) }, hint: "Deliberação 260: cargo de ingresso." },
    { name: "workplace", label: "Lotação", type: "ref", ref: { endpoint: "workplaces", label: (r) => `${r.name} (${r.organ_name})` } },
    { name: "class_level", label: "Classe / nível / referência" },
    { name: "regime", label: "Regime", type: "select", required: true, options: REGIME },
    { name: "admission_form", label: "Forma de admissão", type: "select", required: true, options: ADMISSION_FORM },
    { name: "public_service_start", label: "Ingresso no serviço público", type: "date", required: true },
    { name: "ente_start", label: "Ingresso no ente", type: "date", required: true },
    { name: "career_start", label: "Ingresso na carreira", type: "date" },
    { name: "position_start", label: "Início no cargo atual", type: "date", required: true },
    { name: "statutory_since", label: "Estatutário desde", type: "date" },
    { name: "base_salary", label: "Vencimento base (R$)", type: "money" },
    { name: "weekly_hours", label: "Carga horária (horas semanais)", type: "number" },
    { name: "situation", label: "Situação funcional", type: "select", required: true, options: SITUATION },
    { name: "eligibility", label: "Critério de elegibilidade", type: "select", required: true, options: ELIGIBILITY },
    { name: "segment", label: "Massa (fundo)", type: "select", required: true, options: segments, wide: true },
    ...(hasLifePurchase ? [{ name: "life_purchase", label: "Lote de Compra de Vidas (se massa = Compra de Vidas)", type: "ref" as const, wide: true,
      ref: { endpoint: "life-purchases", label: (r: Record<string, unknown>) => `Lote ${r.number} — corte ${formatDate(String(r.cutoff_date))}` } }] : []),
    { name: "permanence_bonus_since", label: "Abono de permanência desde", type: "date" },
    { name: "complementary_pension", label: "Sujeito à previdência complementar", type: "checkbox" },
    { name: "notes", label: "Observações", type: "textarea" },
  ];
}

const LINK_DEFAULTS = { link_type: 1, regime: "ESTATUTARIO", admission_form: 3, situation: 1, eligibility: 1, segment: "PREVIDENCIARIO" };

export function LinksTab({ personId, canEdit, canCreate }: { personId: string; canEdit: boolean; canCreate: boolean }) {
  const { me } = useSession();
  const hasCV = !!me?.institution?.life_purchase_enabled;
  const { data, isLoading, mutate } = useSWR<Paginated<EmploymentLink>>(`employment-links?person=${personId}&page_size=50`, fetcher);
  const [editing, setEditing] = useState<EmploymentLink | "new" | null>(null);
  const [closing, setClosing] = useState<EmploymentLink | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <>
      <div className="flex items-center justify-between px-1 pb-2">
        <div className="section-label">Vínculos funcionais</div>
        {canCreate && <Button size="sm" variant="outline" onClick={() => setEditing("new")}><Plus /> Novo vínculo</Button>}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" />
            <TableHead>Matrícula</TableHead>
            <TableHead>Cargo / órgão</TableHead>
            <TableHead>Ingresso</TableHead>
            <TableHead>Massa</TableHead>
            <TableHead>Situação</TableHead>
            <TableHead className="w-32" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={7} rows={1} />}
          {data?.results.map((l) => (
            <LinkRow key={l.id} link={l} open={open === l.id} onToggle={() => setOpen(open === l.id ? null : l.id)}
              canEdit={canEdit} onEdit={() => setEditing(l)} onClose={() => setClosing(l)} />
          ))}
          {data?.results.length === 0 && <EmptyRow cols={7} text="Nenhum vínculo." />}
        </TableBody>
      </Table>

      {editing && (
        <FormDialog
          size="lg"
          title={editing === "new" ? "Novo vínculo" : `Vínculo ${editing.registration}`}
          description="Datas e códigos seguem o leiaute SPREV e a Deliberação 260 do TCE-RJ."
          fields={linkFields(hasCV)}
          initial={editing === "new" ? LINK_DEFAULTS : (editing as unknown as Record<string, unknown>)}
          onClose={() => setEditing(null)}
          submit={async (body) => {
            if (editing === "new") await api("employment-links", { method: "POST", body: { ...body, person: personId } });
            else await api(`employment-links/${editing.id}`, { method: "PATCH", body });
            toast.success("Vínculo salvo.");
            mutate();
          }}
        />
      )}
      {closing && (
        <FormDialog
          title={`Encerrar vínculo ${closing.registration}`}
          description="O vínculo não é excluído. O encerramento é registrado no histórico funcional."
          fields={[
            { name: "status", label: "Motivo", type: "select", required: true, options: LINK_CLOSE_STATUS },
            { name: "end_date", label: "Data", type: "date", required: true },
            { name: "end_reason", label: "Descrição", required: true, wide: true },
            { name: "act_type", label: "Natureza do ato", hint: "Portaria, decreto..." },
            { name: "act_number", label: "Número do ato" },
            { name: "act_date", label: "Data do ato", type: "date" },
            { name: "publication", label: "Publicação" },
          ]}
          submitLabel="Encerrar vínculo"
          onClose={() => setClosing(null)}
          submit={async (body) => { await api(`employment-links/${closing.id}/close`, { method: "POST", body }); toast.success("Vínculo encerrado."); mutate(); }}
        />
      )}
    </>
  );
}

function LinkRow({ link: l, open, onToggle, canEdit, onEdit, onClose }: {
  link: EmploymentLink; open: boolean; onToggle: () => void; canEdit: boolean; onEdit: () => void; onClose: () => void;
}) {
  const active = l.status === "ATIVO";
  return (
    <>
      <TableRow className={active ? "" : "opacity-70"}>
        <TableCell>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onToggle} aria-label="Histórico funcional">
            {open ? <ChevronDown /> : <ChevronRight />}
          </Button>
        </TableCell>
        <TableCell className="font-mono text-xs font-semibold">{l.registration}</TableCell>
        <TableCell>
          <div className="font-medium">{l.position_name}</div>
          <div className="text-2xs text-muted-foreground">{l.organ_name}{l.workplace_name ? ` · ${l.workplace_name}` : ""}{l.base_salary ? ` · ${formatCurrency(l.base_salary)}` : ""}</div>
        </TableCell>
        <TableCell className="text-xs">{formatDate(l.position_start)}<div className="text-2xs text-muted-foreground">Serv. público {formatDate(l.public_service_start)}</div></TableCell>
        <TableCell>
          <Badge variant={l.segment === "FINANCEIRO" ? "info" : "default"}>
            {l.segment === "COMPRA_VIDAS" ? `Compra de Vidas · lote ${l.life_purchase_number}` : l.segment === "FINANCEIRO" ? "Financeiro" : "Previdenciário"}
          </Badge>
        </TableCell>
        <TableCell>
          {active ? <Badge variant="success">{l.situation_display}</Badge> : <Badge variant="neutral">{l.status_display} em {formatDate(l.end_date)}</Badge>}
        </TableCell>
        <TableCell className="space-x-1 text-right">
          {canEdit && active && (
            <>
              <Button size="sm" variant="ghost" onClick={onEdit}>Editar</Button>
              <Button size="sm" variant="ghost" onClick={onClose}>Encerrar</Button>
            </>
          )}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/30">
            <EventsPanel link={l} canEdit={canEdit} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function EventsPanel({ link, canEdit }: { link: EmploymentLink; canEdit: boolean }) {
  const { data, mutate } = useSWR<FunctionalEventRow[]>(`functional-events?link=${link.id}`, fetcher);
  const [adding, setAdding] = useState(false);
  return (
    <div className="p-2">
      <div className="mb-2 flex items-center justify-between">
        <div className="section-label">Histórico funcional — matrícula {link.registration}</div>
        {canEdit && <Button size="sm" variant="outline" onClick={() => setAdding(true)}><Plus /> Novo evento</Button>}
      </div>
      {data && data.length === 0 && <p className="text-xs text-muted-foreground">Nenhum evento registrado.</p>}
      <ol className="space-y-1.5">
        {data?.map((e) => (
          <li key={e.id} className="rounded border bg-card px-3 py-2 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{e.event_type_display}</span>
              <span className="text-muted-foreground">{formatDate(e.start_date)}{e.end_date ? ` a ${formatDate(e.end_date)}` : ""}{e.days ? ` · ${e.days} dia(s)` : ""}</span>
              {e.is_absence && !e.contributed && <Badge variant="warning">Sem contribuição</Badge>}
              {e.is_absence && !e.counts_as_service && <Badge variant="warning">Não conta tempo</Badge>}
            </div>
            <div className="mt-0.5">{e.description}</div>
            {(e.act_number || e.act_type) && (
              <div className="text-2xs text-muted-foreground">{e.act_type} {e.act_number}{e.act_date ? ` de ${formatDate(e.act_date)}` : ""}{e.publication ? ` · ${e.publication}` : ""}</div>
            )}
          </li>
        ))}
      </ol>
      {adding && (
        <FormDialog
          title="Novo evento funcional"
          description="Afastamentos sem contribuição são informados à Deliberação 260 e ao cálculo de tempo."
          fields={[
            { name: "event_type", label: "Tipo", type: "select", required: true, options: EVENT_TYPE, wide: true },
            { name: "start_date", label: "Início", type: "date", required: true },
            { name: "end_date", label: "Fim", type: "date" },
            { name: "days", label: "Dias (para faltas)", type: "number" },
            { name: "with_pay", label: "Com remuneração", type: "checkbox" },
            { name: "contributed", label: "Houve contribuição previdenciária", type: "checkbox" },
            { name: "counts_as_service", label: "Conta como tempo de contribuição", type: "checkbox" },
            { name: "act_type", label: "Natureza do ato" },
            { name: "act_number", label: "Número do ato" },
            { name: "act_date", label: "Data do ato", type: "date" },
            { name: "publication", label: "Publicação" },
            { name: "description", label: "Descrição", type: "textarea", required: true },
          ]}
          initial={{ with_pay: true, contributed: true, counts_as_service: true }}
          onClose={() => setAdding(false)}
          submit={async (body) => { await api("functional-events", { method: "POST", body: { ...body, link: link.id } }); toast.success("Evento registrado."); mutate(); }}
        />
      )}
    </div>
  );
}
