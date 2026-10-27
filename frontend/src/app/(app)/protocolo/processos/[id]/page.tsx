"use client";

import { use, useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import {
  Archive, CheckCircle2, Download, Inbox, Loader2, MessageSquare, Pause, Play, RotateCcw, Send, TimerReset, Upload,
} from "lucide-react";

import { DeadlineBadge, StatusBadge } from "@/components/protocolo/deadline-badge";
import { useSession } from "@/components/providers/session-provider";
import { ErrorState } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { FormDialog, type FieldDef } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, download, fetcher } from "@/lib/api";
import { formatCPF, formatDate, formatDateTime } from "@/lib/format";
import type { AttachmentRow, MovementRow, ProcessRow } from "@/lib/types";

type ActionKey = "send" | "despacho" | "suspend" | "resume" | "extend" | "conclude" | "archive" | "reopen";

const TEXT: FieldDef = { name: "text", label: "Despacho / justificativa", type: "textarea", required: true, hint: "Mínimo de 10 caracteres." };
const ACTIONS: Record<ActionKey, { title: string; label: string; fields: FieldDef[]; description?: string }> = {
  send: {
    title: "Enviar a outro setor", label: "Enviar", description: "O setor de destino precisará receber o processo.",
    fields: [{ name: "to_sector", label: "Setor de destino", type: "ref", required: true, wide: true,
      ref: { endpoint: "protocol/sectors", label: (r) => `${r.code} - ${r.name}` } }, TEXT],
  },
  despacho: { title: "Registrar despacho", label: "Registrar", fields: [{ ...TEXT, label: "Despacho" }] },
  suspend: { title: "Sobrestar processo", label: "Sobrestar", description: "A contagem do prazo fica suspensa até a retomada.", fields: [TEXT] },
  resume: { title: "Retomar processo", label: "Retomar", description: "O prazo será estendido pelos dias em que ficou sobrestado.", fields: [TEXT] },
  extend: {
    title: "Prorrogar prazo", label: "Prorrogar",
    fields: [{ name: "days", label: "Dias de prorrogação", type: "number", required: true }, TEXT],
  },
  conclude: { title: "Concluir processo", label: "Concluir", fields: [{ ...TEXT, label: "Despacho final" }] },
  archive: { title: "Arquivar processo", label: "Arquivar", fields: [{ ...TEXT, label: "Despacho de arquivamento" }] },
  reopen: { title: "Desarquivar / reabrir", label: "Reabrir", fields: [TEXT] },
};

export default function ProcessPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequirePermission module="protocolo.processos">
      <ProcessDetail id={id} />
    </RequirePermission>
  );
}

function ProcessDetail({ id }: { id: string }) {
  const { can } = useSession();
  const { data: p, error, mutate } = useSWR<ProcessRow>(`protocol/processes/${id}`, fetcher);
  const moves = useSWR<MovementRow[]>(`protocol/processes/${id}/movements`, fetcher);
  const [action, setAction] = useState<ActionKey | null>(null);
  const [receiving, setReceiving] = useState(false);

  if (error) return <ErrorState error={error} />;
  if (!p) return <div className="h-64 animate-pulse rounded-lg bg-muted" />;

  const refresh = () => { mutate(); moves.mutate(); };
  const canEdit = can("protocolo.processos", "editar");
  const open = p.status === "EM_TRAMITACAO";
  const closed = p.status === "CONCLUIDO" || p.status === "ARQUIVADO";

  const receive = async () => {
    setReceiving(true);
    try {
      await api(`protocol/processes/${id}/receive`, { method: "POST" });
      toast.success("Processo recebido.");
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setReceiving(false);
    }
  };

  const btn = (key: ActionKey, Icon: typeof Send, variant: "default" | "outline" = "outline") => (
    <Button key={key} size="sm" variant={variant} onClick={() => setAction(key)}><Icon /> {ACTIONS[key].label}</Button>
  );

  return (
    <>
      <PageHeader
        title={`Processo ${p.code}`}
        description={<span className="flex flex-wrap items-center gap-2">{p.subject} <StatusBadge p={p} /> <DeadlineBadge p={p} /></span>}
        breadcrumb={[{ label: "Protocolo", href: "/protocolo" }, { label: p.code }]}
        actions={canEdit && (
          <>
            {p.pending_receipt && !closed && (
              <Button size="sm" onClick={receive} disabled={receiving}>{receiving ? <Loader2 className="animate-spin" /> : <Inbox />} Receber</Button>
            )}
            {open && !p.pending_receipt && [btn("send", Send, "default"), btn("despacho", MessageSquare), btn("suspend", Pause)]}
            {p.status === "SOBRESTADO" && [btn("resume", Play, "default"), btn("despacho", MessageSquare)]}
            {open && can("protocolo.configuracao", "editar") && btn("extend", TimerReset)}
            {!closed && !p.pending_receipt && can("protocolo.processos", "fechar") && [btn("conclude", CheckCircle2), btn("archive", Archive)]}
            {closed && can("protocolo.processos", "reabrir") && btn("reopen", RotateCcw)}
          </>
        )}
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-1">
          <CardHeader><CardTitle>Dados do processo</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            <Info label="Tipo" value={p.process_type_name} />
            <Info label="Interessado" value={
              p.interested ? <Link href={`/cadastros/pessoas/${p.interested}`} className="text-primary hover:underline">{p.interested_name}</Link> : p.interested_name
            } />
            {p.interested_cpf && <Info label="CPF/CNPJ" value={p.interested_cpf.length === 11 ? formatCPF(p.interested_cpf) : p.interested_cpf} />}
            <Info label="Prioridade" value={p.priority_display} />
            {p.external_number && <Info label="Nº de origem" value={p.external_number} />}
            <Info label="Aberto em" value={formatDateTime(p.opened_at)} />
            <Info label="Setor atual" value={`${p.current_sector_code} - ${p.current_sector_name}`} />
            <Info label="Prazo" value={`${p.deadline_days} dia(s) ${p.business_days ? "úteis" : "corridos"} — vence ${formatDate(p.due_date)}`} />
            {p.sector_due_date && <Info label="Prazo no setor" value={formatDate(p.sector_due_date)} />}
            {p.suspended_since && <Info label="Sobrestado desde" value={formatDate(p.suspended_since)} />}
            {p.closed_at && <Info label="Encerrado em" value={formatDateTime(p.closed_at)} />}
            {p.description && <div className="border-t pt-2"><div className="section-label mb-1">Descrição</div><p className="whitespace-pre-line">{p.description}</p></div>}
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader><CardTitle>Tramitação</CardTitle></CardHeader>
          <CardContent>
            <ol className="relative space-y-3 border-l pl-4">
              {moves.data?.map((m) => (
                <li key={m.id} className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-card bg-primary" />
                  <div className="flex flex-wrap items-baseline gap-2 text-xs">
                    <span className="font-semibold">{m.kind_display}</span>
                    {(m.from_sector_code || m.to_sector_code) && (
                      <span className="text-muted-foreground">{m.from_sector_code}{m.from_sector_code && m.to_sector_code ? " → " : ""}{m.to_sector_code}</span>
                    )}
                    <span className="text-2xs text-muted-foreground">{formatDateTime(m.occurred_at)} · {m.user_name || "Sistema"}</span>
                  </div>
                  {m.text && <p className="mt-0.5 whitespace-pre-line text-xs">{m.text}</p>}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <Attachments process={p} canEdit={canEdit && !closed} />
      </div>

      {action && (
        <FormDialog
          title={ACTIONS[action].title}
          description={ACTIONS[action].description}
          fields={ACTIONS[action].fields}
          submitLabel={ACTIONS[action].label}
          onClose={() => setAction(null)}
          submit={async (body) => {
            await api(`protocol/processes/${id}/${action}`, { method: "POST", body });
            toast.success("Andamento registrado.");
            refresh();
          }}
        />
      )}
    </>
  );
}

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="col-span-2 font-medium">{value}</span>
    </div>
  );
}

function Attachments({ process, canEdit }: { process: ProcessRow; canEdit: boolean }) {
  const { data, mutate } = useSWR<AttachmentRow[]>(`protocol/processes/${process.id}/attachments`, fetcher);
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !description.trim()) { toast.error("Informe a descrição e selecione o arquivo."); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("description", description);
      fd.append("file", file);
      const res = await fetch(`/api/backend/protocol/processes/${process.id}/attach`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || Object.values(body).flat().join(" ") || "Falha no envio.");
      toast.success("Anexo incluído.");
      setDescription("");
      if (fileRef.current) fileRef.current.value = "";
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="xl:col-span-3">
      <CardHeader><CardTitle>Anexos</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {canEdit && (
          <div className="grid gap-3 rounded-md border bg-muted/40 p-3 sm:grid-cols-3">
            <FormField label="Descrição" htmlFor="att-desc"><Input id="att-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></FormField>
            <FormField label="Arquivo (PDF, JPG ou PNG até 10 MB)" htmlFor="att-file"><Input id="att-file" ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" className="py-1" /></FormField>
            <div className="flex items-end"><Button onClick={upload} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Upload />} Anexar</Button></div>
          </div>
        )}
        {data?.length === 0 && <p className="text-xs text-muted-foreground">Nenhum anexo.</p>}
        <ul className="divide-y rounded-md border">
          {data?.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
              <div>
                <div className="font-medium">{a.description}</div>
                <div className="text-2xs text-muted-foreground">{a.file_name} · {formatDateTime(a.created_at)} · {a.uploaded_by} · SHA-256 {a.sha256.slice(0, 12)}…</div>
              </div>
              <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Baixar"
                onClick={() => download(`protocol/processes/${process.id}/attachments/${a.id}/download`, a.file_name).catch((e) => toast.error((e as Error).message))}>
                <Download />
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
