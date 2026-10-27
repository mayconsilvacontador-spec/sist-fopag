"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { Ban, CheckCircle2, CircleDashed, Download, FileCheck2, Loader2, RotateCcw, Upload } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { api, download } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ChecklistItemRow, ChecklistResponse, ChecklistSectorCode, Concession } from "@/lib/types";

const SECTORS: ChecklistSectorCode[] = ["BENEFICIOS", "JURIDICO", "CONTROLE", "PRESIDENCIA", "FOLHA"];

/** Permissão para anexar no checklist de cada setor (espelha o backend). */
export function sectorPerm(kind: Concession["kind"]): Record<ChecklistSectorCode, [string, string]> {
  const mod = kind === "APOSENTADORIA" ? "concessao.aposentadoria" : kind === "PENSAO" ? "concessao.pensao" : "concessao.revisao";
  return {
    BENEFICIOS: [mod, "editar"], JURIDICO: ["concessao.juridico", "aprovar"],
    CONTROLE: ["concessao.controle_interno", "aprovar"], PRESIDENCIA: ["concessao.presidencia", "aprovar"],
    FOLHA: ["concessao.implantacao", "aprovar"],
  };
}

/**
 * Processo digital: documentos exigidos por setor. O setor que está com o processo anexa (PDF/JPG/PNG) ou justifica
 * “não se aplica”; os documentos do sistema são gerados no ato do setor. Cada arquivo guarda o código SHA-256.
 */
export function ChecklistPanel({ c, data, onChanged }: { c: Concession; data?: ChecklistResponse; onChanged: () => void }) {
  const { can } = useSession();
  const [waiving, setWaiving] = useState<ChecklistItemRow | null>(null);
  if (!data) return <div className="h-32 animate-pulse rounded-lg bg-muted" />;
  const perms = sectorPerm(c.kind);
  const sectors = SECTORS.filter((s) => data.itens.some((i) => i.sector === s));
  const total = data.itens.filter((i) => i.required).length;
  const done = data.itens.filter((i) => i.required && i.status !== "PENDENTE").length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5"><FileCheck2 className="h-4 w-4 text-primary" /> Processo digital — documentos</CardTitle>
        <span className="text-2xs text-muted-foreground">{done} de {total} obrigatório(s) cumprido(s)</span>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <p className="text-muted-foreground">
          Cada setor só libera o processo com os documentos obrigatórios do seu checklist. Ao liberar (com senha), o checklist é
          assinado: o sistema calcula um código SHA-256 que fica na trilha e no andamento do Protocolo.
        </p>
        {sectors.map((s) => {
          const items = data.itens.filter((i) => i.sector === s);
          const current = data.setor_atual === s;
          const editable = current && can(...perms[s]) && !["SOBRESTADO", "DESISTENCIA", "INDEFERIDO", "ANULADO"].includes(c.stage);
          return (
            <div key={s} className={cn("rounded-md border", current && "border-primary/50")}>
              <div className={cn("flex items-center justify-between border-b px-3 py-1.5", current ? "bg-primary-soft" : "bg-muted/40")}>
                <span className="font-semibold">{items[0].sector_display}</span>
                {current ? <Badge variant="info">com o processo</Badge>
                  : items.every((i) => !i.required || i.status !== "PENDENTE") ? <Badge variant="success">completo</Badge>
                    : <Badge variant="neutral">aguardando</Badge>}
              </div>
              <ul className="divide-y">
                {items.map((i) => <ItemRow key={i.id} c={c} item={i} editable={editable} cadastro={data.cadastro} onChanged={onChanged} onWaive={() => setWaiving(i)} />)}
              </ul>
            </div>
          );
        })}
      </CardContent>
      {waiving && <WaiveDialog c={c} item={waiving} onClose={() => setWaiving(null)} onDone={() => { setWaiving(null); onChanged(); }} />}
    </Card>
  );
}

function ItemRow({ c, item: i, editable, cadastro, onChanged, onWaive }: {
  c: Concession; item: ChecklistItemRow; editable: boolean; cadastro?: ChecklistResponse["cadastro"]; onChanged: () => void; onWaive: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<File | null>(null);
  // Comprovante de residência e identidade: conferir/atualizar os dados do Cadastro Único antes de anexar
  const pick = (file: File) => (i.person_doc_type === "RESIDENCIA" || i.person_doc_type === "IDENTIDADE" ? setConfirm(file) : upload(file));
  const upload = async (file: File, dados?: Record<string, string>) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (dados) fd.append("dados", JSON.stringify(dados));
      const res = await fetch(`/api/backend/concessoes/${c.id}/checklist/${i.id}/attach`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Falha ao anexar.");
      toast.success(i.person_doc_type ? "Documento anexado e guardado no Cadastro Único." : "Documento anexado.");
      setConfirm(null);
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };
  const reopen = async () => {
    try {
      await api(`concessoes/${c.id}/checklist/${i.id}/reopen`, { method: "POST", body: {} });
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };
  const get = () => {
    const path = i.attachment ? `protocol/processes/${c.process}/attachments/${i.attachment}/download`
      : `concessoes/${c.id}/documents/${i.document}/download`;
    download(path, i.file_name).catch((e) => toast.error((e as Error).message));
  };
  const Icon = i.status === "CUMPRIDO" ? CheckCircle2 : i.status === "NAO_SE_APLICA" ? Ban : CircleDashed;
  return (
    <li className="flex flex-wrap items-start justify-between gap-2 px-3 py-2">
      <div className="flex min-w-0 flex-1 gap-2">
        <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", i.status === "CUMPRIDO" ? "text-success" : i.status === "NAO_SE_APLICA" ? "text-muted-foreground" : i.required ? "text-warning" : "text-muted-foreground")} />
        <div className="min-w-0">
          <div className="font-medium">{i.name}{!i.required && <span className="font-normal text-muted-foreground"> (opcional)</span>}
            {i.source === "SISTEMA" && <Badge variant="neutral" className="ml-1">gerado pelo sistema</Badge>}</div>
          {i.help_text && i.status === "PENDENTE" && <div className="text-2xs text-muted-foreground">{i.help_text}</div>}
          {i.status === "CUMPRIDO" && (
            <div className="text-2xs text-muted-foreground">
              {i.file_name} · SHA-256 <span className="font-mono" title={i.sha256}>{i.sha256.slice(0, 16)}…</span>
              {i.done_by_name && <> · {i.done_by_name}, {formatDateTime(i.done_at)}</>}
            </div>
          )}
          {i.status === "NAO_SE_APLICA" && <div className="text-2xs text-muted-foreground">Não se aplica: {i.note} ({i.done_by_name})</div>}
          {i.person_doc_type && <div className="text-2xs text-primary">Também guardado no Cadastro Único{i.person_document ? " ✓" : ""}</div>}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {i.status === "CUMPRIDO" && i.file_id && (
          <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Baixar" onClick={get}><Download /></Button>
        )}
        {editable && i.source === "ANEXO" && (
          <>
            <input ref={input} type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden" onChange={(e) => e.target.files?.[0] && pick(e.target.files[0])} />
            <Button size="sm" variant={i.status === "PENDENTE" ? "default" : "outline"} disabled={busy} onClick={() => input.current?.click()}>
              {busy ? <Loader2 className="animate-spin" /> : <Upload />} {i.status === "CUMPRIDO" ? "Substituir" : "Anexar"}
            </Button>
            {i.status === "PENDENTE" && <Button size="sm" variant="ghost" onClick={onWaive}>Não se aplica</Button>}
            {i.status === "NAO_SE_APLICA" && <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Reabrir" onClick={reopen}><RotateCcw /></Button>}
          </>
        )}
      </div>
      {confirm && <ConfirmDataDialog item={i} file={confirm} cadastro={cadastro} busy={busy}
        onClose={() => { setConfirm(null); if (input.current) input.current.value = ""; }}
        onConfirm={(dados) => upload(confirm, dados)} />}
    </li>
  );
}

const ADDRESS_FIELDS: [string, string, string][] = [
  ["cep", "CEP", "sm:col-span-1"], ["street", "Logradouro", "sm:col-span-3"], ["number", "Número", "sm:col-span-1"],
  ["complement", "Complemento", "sm:col-span-1"], ["district", "Bairro", "sm:col-span-2"], ["city", "Cidade", "sm:col-span-3"], ["uf", "UF", "sm:col-span-1"],
];
const ID_FIELDS: [string, string, string][] = [
  ["rg_number", "Número do RG", "sm:col-span-2"], ["rg_issuer", "Órgão emissor", "sm:col-span-1"], ["rg_uf", "UF", "sm:col-span-1"], ["rg_date", "Expedição", "sm:col-span-2"],
];

/** Conferência dos dados do documento: o que for alterado atualiza o Cadastro Único (endereço = nova vigência). */
function ConfirmDataDialog({ item, file, cadastro, busy, onClose, onConfirm }: {
  item: ChecklistItemRow; file: File; cadastro?: ChecklistResponse["cadastro"]; busy: boolean;
  onClose: () => void; onConfirm: (dados?: Record<string, string>) => void;
}) {
  const addr = item.person_doc_type === "RESIDENCIA";
  const fields = addr ? ADDRESS_FIELDS : ID_FIELDS;
  const initial = (addr ? cadastro?.endereco : cadastro?.identidade) ?? {};
  const [v, setV] = useState<Record<string, string>>(Object.fromEntries(fields.map(([k]) => [k, String((initial as Record<string, string>)[k] ?? "")])));
  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>{addr ? "Conferir endereço do comprovante" : "Conferir dados da identidade"}</DialogTitle>
          <DialogDescription>
            {cadastro?.nome} · arquivo {file.name}. Confira com o documento: se algo mudou, corrija aqui e o Cadastro Único é atualizado
            {addr ? " (o endereço anterior fica no histórico)" : ""}. O documento também é guardado nos documentos da pessoa.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="grid gap-3 text-xs sm:grid-cols-6">
          {fields.map(([k, label, span]) => (
            <label key={k} className={cn("space-y-1", span)}>
              <span className="font-medium">{label}</span>
              <Input type={k === "rg_date" ? "date" : "text"} value={v[k]} onChange={(e) => setV((s) => ({ ...s, [k]: e.target.value }))} />
            </label>
          ))}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button variant="outline" onClick={() => onConfirm()} disabled={busy}>Anexar sem alterar dados</Button>
          <Button onClick={() => onConfirm(v)} disabled={busy}>{busy && <Loader2 className="animate-spin" />} Anexar e atualizar cadastro</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function WaiveDialog({ c, item, onClose, onDone }: { c: Concession; item: ChecklistItemRow; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Documento não se aplica</DialogTitle>
          <DialogDescription>{item.name}. A justificativa fica registrada no processo e entra na assinatura do checklist.</DialogDescription>
        </DialogHeader>
        <DialogBody><Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Justificativa (mínimo de 15 caracteres)" /></DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button disabled={busy || note.trim().length < 15} onClick={async () => {
            setBusy(true);
            try {
              await api(`concessoes/${c.id}/checklist/${item.id}/waive`, { method: "POST", body: { note } });
              onDone();
            } catch (err) {
              toast.error((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}>{busy && <Loader2 className="animate-spin" />} Registrar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
