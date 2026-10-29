"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { FileText, Loader2, Package, Pencil, Plus, Power } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox, Input, Select, Textarea } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher } from "@/lib/api";
import { formatDate } from "@/lib/format";

type Norm = {
  id: string; kind: string; kind_display: string; number: string; date: string | null; publication_date: string | null;
  valid_from: string | null; valid_to: string | null; summary: string; subjects: string[]; url: string; file_name: string;
  has_file: boolean; active: boolean; citation: string; rules_count: number;
};
type Packages = { pacotes: { codigo: string; label: string; description: string; needs_reform: boolean }[]; pacote_atual: string; regras_ativas: number; regras_total: number };

const KINDS = [
  ["EMENDA_LOM", "Emenda à Lei Orgânica"], ["LEI_ORGANICA", "Lei Orgânica / Constituição Estadual"],
  ["LEI_COMPLEMENTAR", "Lei Complementar"], ["LEI", "Lei"], ["DECRETO", "Decreto"], ["PORTARIA", "Portaria"],
  ["RESOLUCAO", "Resolução"], ["EMENDA_CF", "Emenda Constitucional (federal)"], ["OUTRO", "Outra norma"],
];
const SUBJECTS = [["APOSENTADORIA", "Aposentadoria"], ["PENSAO", "Pensão por morte"], ["CONTRIBUICAO", "Contribuições e alíquotas"],
  ["ORGANIZACAO", "Organização do RPPS"], ["FOLHA", "Folha e benefícios"], ["OUTRO", "Outro assunto"]];

export default function LegislacaoPage() {
  return (
    <RequirePermission module="previdenciaria.regras">
      <Legislacao />
    </RequirePermission>
  );
}

function Legislacao() {
  const { can } = useSession();
  const norms = useSWR<Norm[]>("previdencia/legislacao", fetcher);
  const [editing, setEditing] = useState<Norm | "new" | null>(null);
  const canEdit = can("previdenciaria.regras", "editar");

  const toggle = async (n: Norm) => {
    try {
      await api(`previdencia/legislacao/${n.id}/inativar`, { method: "POST", body: {} });
      norms.mutate();
    } catch (err) { toast.error((err as Error).message); }
  };

  return (
    <>
      <PageHeader title="Legislação do RPPS"
        description="As normas próprias deste ente (leis, emendas à lei orgânica, decretos) e o pacote de regras de aposentadoria que o sistema usa. A citação da norma sai na portaria, no parecer e na Ficha FATIMA."
        breadcrumb={[{ label: "Gestão Previdenciária" }, { label: "Legislação do RPPS" }]}
        actions={can("previdenciaria.regras", "incluir") && <Button onClick={() => setEditing("new")}><Plus /> Nova norma</Button>} />

      <Card className="mb-4">
        <CardHeader><CardTitle>Normas cadastradas</CardTitle></CardHeader>
        <Table>
          <TableHeader><TableRow><TableHead>Norma</TableHead><TableHead>Assuntos</TableHead><TableHead>Vigência</TableHead>
            <TableHead>Regras</TableHead><TableHead className="w-28" /></TableRow></TableHeader>
          <TableBody>
            {norms.isLoading && <LoadingRows cols={5} rows={2} />}
            {norms.data?.map((n) => (
              <TableRow key={n.id} className={n.active ? "" : "opacity-60"}>
                <TableCell>
                  <div className="font-medium">{n.citation} {!n.active && <Badge variant="neutral">Inativa</Badge>}</div>
                  {n.summary && <div className="text-2xs text-muted-foreground">{n.summary}</div>}
                  {n.publication_date && <div className="text-2xs text-muted-foreground">Publicada em {formatDate(n.publication_date)}</div>}
                </TableCell>
                <TableCell className="text-xs">{n.subjects.map((s) => SUBJECTS.find((x) => x[0] === s)?.[1] ?? s).join(", ") || "—"}</TableCell>
                <TableCell className="text-xs">{n.valid_from ? `desde ${formatDate(n.valid_from)}` : "—"}{n.valid_to ? ` até ${formatDate(n.valid_to)}` : ""}</TableCell>
                <TableCell>{n.rules_count || "—"}</TableCell>
                <TableCell className="space-x-1 whitespace-nowrap text-right">
                  {n.has_file && <Button asChild variant="ghost" size="icon" className="h-7 w-7" title="Ver PDF"><a href={`/api/backend/previdencia/legislacao/${n.id}/arquivo`} target="_blank" rel="noreferrer"><FileText /></a></Button>}
                  {canEdit && <Button variant="ghost" size="icon" className="h-7 w-7" title="Editar" onClick={() => setEditing(n)}><Pencil /></Button>}
                  {canEdit && <Button variant="ghost" size="icon" className="h-7 w-7" title={n.active ? "Inativar" : "Reativar"} onClick={() => toggle(n)}><Power /></Button>}
                </TableCell>
              </TableRow>
            ))}
            {norms.data?.length === 0 && <EmptyRow cols={5} text="Nenhuma norma cadastrada. Cadastre a lei da reforma (ou a lei de organização do RPPS) do ente." />}
          </TableBody>
        </Table>
      </Card>

      <PackagesCard norms={norms.data ?? []} canEdit={canEdit} />
      {editing && <NormDialog norm={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => norms.mutate()} />}
    </>
  );
}

function PackagesCard({ norms, canEdit }: { norms: Norm[]; canEdit: boolean }) {
  const { data, mutate } = useSWR<Packages>("previdencia/pacotes-regras", fetcher);
  const [pacote, setPacote] = useState("");
  const [reforma, setReforma] = useState("");
  const [norma, setNorma] = useState("");
  const [just, setJust] = useState("");
  const [busy, setBusy] = useState(false);
  if (!data) return <Card><CardContent className="p-6"><Loader2 className="animate-spin" /></CardContent></Card>;
  const sel = data.pacotes.find((p) => p.codigo === pacote);
  const atual = data.pacotes.find((p) => p.codigo === data.pacote_atual);

  const aplicar = async () => {
    if (data.regras_ativas > 0 && !window.confirm("As regras atuais serão atualizadas para o pacote escolhido (o valor anterior fica na auditoria). Concessões já feitas não mudam. Continuar?")) return;
    setBusy(true);
    try {
      const r = await api<{ criadas: number; atualizadas: number; inativadas: number; aviso: string }>("previdencia/pacotes-regras", {
        method: "POST", body: { pacote, reforma: reforma || undefined, norma: norma || undefined, justificativa: just } });
      toast.success(`Pacote aplicado: ${r.criadas} regra(s) nova(s), ${r.atualizadas} atualizada(s), ${r.inativadas} inativada(s).`);
      if (r.aviso) toast.warning(r.aviso);
      setJust("");
      mutate();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Package className="h-4 w-4" /> Pacote de regras de aposentadoria</CardTitle>
        <Link href="/previdenciaria/regras" className="text-xs font-semibold text-primary hover:underline">Ver e ajustar as regras →</Link></CardHeader>
      <CardContent className="space-y-4 text-xs">
        <p>Em uso: <b>{atual ? atual.label : data.regras_ativas ? "regras cadastradas sem pacote (carga anterior)" : "nenhuma regra ainda"}</b> · {data.regras_ativas} regra(s) ativa(s).</p>
        {canEdit && (
          <>
            <div className="grid gap-3 lg:grid-cols-3">
              {data.pacotes.map((p) => (
                <button key={p.codigo} type="button" onClick={() => setPacote(p.codigo)}
                  className={`rounded-lg border p-3 text-left transition-colors ${pacote === p.codigo ? "border-primary bg-primary-soft" : "hover:bg-muted"}`}>
                  <div className="font-semibold text-primary-strong">{p.label}</div>
                  <div className="mt-1 text-muted-foreground">{p.description}</div>
                </button>
              ))}
            </div>
            {sel && (
              <div className="grid gap-3 rounded-lg border bg-muted/30 p-3 sm:grid-cols-2 lg:grid-cols-4">
                {sel.needs_reform && (
                  <FormField label="Reforma local vale a partir de" htmlFor="pk-ref" hint="Regras antigas: só quem cumpriu os requisitos até a véspera.">
                    <Input id="pk-ref" type="date" value={reforma} onChange={(e) => setReforma(e.target.value)} />
                  </FormField>
                )}
                <FormField label="Norma local que fundamenta" htmlFor="pk-norma" className={sel.needs_reform ? "" : "sm:col-span-2"}>
                  <Select id="pk-norma" value={norma} onChange={(e) => setNorma(e.target.value)}>
                    <option value="">— nenhuma —</option>{norms.filter((n) => n.active).map((n) => <option key={n.id} value={n.id}>{n.citation}</option>)}
                  </Select>
                </FormField>
                <FormField label="Justificativa" htmlFor="pk-just" className="sm:col-span-2">
                  <Input id="pk-just" value={just} onChange={(e) => setJust(e.target.value)} placeholder="Ex.: Implantação — LC nº 45/2021" />
                </FormField>
                <div className="flex items-end sm:col-span-2 lg:col-span-4">
                  <Button onClick={aplicar} disabled={busy || just.trim().length < 10 || (sel.needs_reform && !reforma)}>
                    {busy ? <Loader2 className="animate-spin" /> : <Package />} Aplicar pacote
                  </Button>
                  <span className="ml-3 text-muted-foreground">Depois confira cada regra (idades, tempos, pontos) com a lei do ente.</span>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function NormDialog({ norm, onClose, onSaved }: { norm: Norm | null; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<Record<string, string>>({
    kind: norm?.kind ?? "LEI_COMPLEMENTAR", number: norm?.number ?? "", date: norm?.date ?? "", publication_date: norm?.publication_date ?? "",
    valid_from: norm?.valid_from ?? "", valid_to: norm?.valid_to ?? "", summary: norm?.summary ?? "", url: norm?.url ?? "",
  });
  const [subjects, setSubjects] = useState<string[]>(norm?.subjects ?? ["APOSENTADORIA"]);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF((x) => ({ ...x, [k]: e.target.value }));

  const save = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      Object.entries(f).forEach(([k, v]) => fd.append(k, v));
      subjects.forEach((s) => fd.append("subjects", s));
      const file = fileRef.current?.files?.[0];
      if (file) fd.append("file", file);
      const r = await fetch(`/api/backend/previdencia/legislacao${norm ? `/${norm.id}/salvar` : ""}`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || "Não foi possível salvar.");
      toast.success("Norma salva.");
      onSaved();
      onClose();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg">
        <DialogHeader><DialogTitle>{norm ? norm.citation : "Nova norma"}</DialogTitle>
          <DialogDescription>Cadastre a norma do ente e anexe o PDF publicado. As regras e as concessões passam a citá-la.</DialogDescription></DialogHeader>
        <DialogBody className="grid gap-3 sm:grid-cols-2">
          <FormField label="Tipo" htmlFor="n-kind"><Select id="n-kind" value={f.kind} onChange={set("kind")}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></FormField>
          <FormField label="Número" htmlFor="n-num"><Input id="n-num" value={f.number} onChange={set("number")} placeholder="ex.: 106/2025" /></FormField>
          <FormField label="Data da norma" htmlFor="n-date"><Input id="n-date" type="date" value={f.date} onChange={set("date")} /></FormField>
          <FormField label="Data da publicação" htmlFor="n-pub"><Input id="n-pub" type="date" value={f.publication_date} onChange={set("publication_date")} /></FormField>
          <FormField label="Vigência a partir de" htmlFor="n-vf"><Input id="n-vf" type="date" value={f.valid_from} onChange={set("valid_from")} /></FormField>
          <FormField label="Vigência até (se revogada)" htmlFor="n-vt"><Input id="n-vt" type="date" value={f.valid_to} onChange={set("valid_to")} /></FormField>
          <FormField label="Ementa / resumo" htmlFor="n-sum" className="sm:col-span-2"><Textarea id="n-sum" value={f.summary} onChange={set("summary")} /></FormField>
          <div className="sm:col-span-2">
            <div className="mb-1 text-xs font-medium">Assuntos</div>
            <div className="flex flex-wrap gap-3 text-xs">
              {SUBJECTS.map(([v, l]) => (
                <label key={v} className="flex items-center gap-1.5"><Checkbox checked={subjects.includes(v)}
                  onChange={(e) => setSubjects((s) => (e.target.checked ? [...s, v] : s.filter((x) => x !== v)))} /> {l}</label>
              ))}
            </div>
          </div>
          <FormField label="Endereço na internet (opcional)" htmlFor="n-url"><Input id="n-url" value={f.url} onChange={set("url")} placeholder="https://..." /></FormField>
          <FormField label={norm?.has_file ? `PDF (atual: ${norm.file_name}) — envie outro para trocar` : "PDF da norma publicada"} htmlFor="n-file">
            <Input id="n-file" ref={fileRef} type="file" accept="application/pdf" className="py-1" />
          </FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={save} disabled={busy || !f.number.trim()}>{busy && <Loader2 className="animate-spin" />} Salvar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
