"use client";

/**
 * Transmissão direta ao eSocial: certificado A1, teste de conexão, envio de lotes e consulta do retorno.
 * O certificado e a senha ficam criptografados no servidor; cada envio pede a senha do usuário.
 */
import { useMemo, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { KeyRound, Loader2, PlugZap, RefreshCw, Send, ShieldAlert, ShieldCheck, Upload } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Cert = {
  id: string; titular: string; documento: string; emissor: string; serie: string; impressao_digital: string;
  valido_de: string; valido_ate: string; vencido: boolean; dias_para_vencer: number; enviado_em: string; enviado_por: string;
  ultimo_teste: string | null; resultado_teste: string;
};
type Info = {
  certificado: Cert | null; ambiente: number; ambiente_display: string; chave_configurada: boolean;
  prontos: Record<string, number>; limite_lote: number;
};
type Batch = {
  id: string; environment_display: string; group: number; group_display: string; status: "RECUSADO" | "PROCESSANDO" | "PROCESSADO";
  status_display: string; protocol: string; sent_at: string; response_code: string; response_message: string; queried_at: string | null;
  queries: number; created_by_name: string; total: number; resumo: Record<string, number>;
};
type Ev = { id: string; event_type: string; event_type_display: string; reference: string; period: string; status: string; environment: number; created_at: string };

const GROUPS: { n: number; label: string; types: string[] }[] = [
  { n: 2, label: "Não periódicos (S-2400, S-2410, S-2420)", types: ["S-2400", "S-2410", "S-2420"] },
  { n: 3, label: "Periódicos (S-1207, S-1210, S-1299)", types: ["S-1207", "S-1210", "S-1299"] },
  { n: 1, label: "Tabelas (S-1010)", types: ["S-1010"] },
];
const fmtDoc = (d: string) => d.length === 14 ? d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5")
  : d.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, "$1.$2.$3-$4");

export function TransmissionPage() {
  return <RequirePermission module="esocial.transmissao"><Transmission /></RequirePermission>;
}

function Transmission() {
  const { can } = useSession();
  const info = useSWR<Info>("esocial/transmissao", fetcher);
  const [page, setPage] = useState(1);
  const batches = useSWR<Paginated<Batch>>(`esocial/lotes${qs({ page })}`, fetcher, { keepPreviousData: true });
  const [uploading, setUploading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [querying, setQuerying] = useState<string | null>(null);
  const refresh = () => { info.mutate(); batches.mutate(); };
  const c = info.data?.certificado;
  const test = async () => {
    setTesting(true);
    try {
      const r = await api<{ ok: boolean; mensagem: string }>("esocial/transmissao/testar", { method: "POST", body: {} });
      if (r.ok) toast.success(r.mensagem); else toast.error(r.mensagem);
      info.mutate();
    } catch (err) { toast.error((err as Error).message); } finally { setTesting(false); }
  };
  const query = async (b: Batch) => {
    setQuerying(b.id);
    try {
      const r = await api<Batch>(`esocial/lotes/${b.id}/consultar`, { method: "POST", body: {} });
      if (r.status === "PROCESSADO") toast.success(`Lote processado: ${r.resumo.ACEITO ?? 0} aceito(s), ${r.resumo.REJEITADO ?? 0} rejeitado(s).`);
      else if (r.status === "RECUSADO") toast.error(`Lote com erro: ${r.response_message || r.response_code}. Os eventos voltaram para "Pronto".`);
      else toast.info("O eSocial ainda está processando o lote. Consulte de novo em alguns minutos.");
      refresh();
    } catch (err) { toast.error((err as Error).message); } finally { setQuerying(null); }
  };
  return (
    <>
      <PageHeader title="Transmissão ao eSocial" description="Envio direto dos eventos ao eSocial com o certificado digital do órgão: o SIST assina, envia em lote e busca o retorno (recibo ou erro) de cada evento."
        breadcrumb={[{ label: "eSocial RPPS" }, { label: "Transmissão" }]} />
      {info.error && <ErrorState error={info.error} />}
      {info.data && (
        <div className="mb-4 grid gap-4 xl:grid-cols-12">
          <Card className="xl:col-span-7">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">{c && !c.vencido ? <ShieldCheck className="h-4 w-4 text-success" /> : <ShieldAlert className="h-4 w-4 text-warning" />} Certificado digital</CardTitle>
              <Badge variant={info.data.ambiente === 1 ? "critical" : "info"}>{info.data.ambiente_display}</Badge>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              {!info.data.chave_configurada && <div className="rounded border border-critical-border bg-critical-soft p-2">A chave de criptografia do servidor não está configurada (ESOCIAL_CERT_KEY). Peça ao suporte técnico.</div>}
              {c ? (
                <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                  <div><span className="text-muted-foreground">Titular: </span><b>{c.titular}</b></div>
                  <div><span className="text-muted-foreground">CNPJ/CPF: </span>{fmtDoc(c.documento)}</div>
                  <div><span className="text-muted-foreground">Válido até: </span><span className={cn(c.vencido ? "text-critical" : c.dias_para_vencer <= 30 ? "text-warning" : "")}>{formatDate(c.valido_ate)}{c.vencido ? " (vencido)" : ` (${c.dias_para_vencer} dias)`}</span></div>
                  <div><span className="text-muted-foreground">Enviado em: </span>{formatDateTime(c.enviado_em)}{c.enviado_por ? ` por ${c.enviado_por}` : ""}</div>
                  <div className="sm:col-span-2 truncate"><span className="text-muted-foreground">Emissor: </span>{c.emissor}</div>
                  {c.ultimo_teste && <div className="sm:col-span-2"><span className="text-muted-foreground">Último teste ({formatDateTime(c.ultimo_teste)}): </span>{c.resultado_teste}</div>}
                </div>
              ) : <p>Nenhum certificado cadastrado. Envie o certificado <b>A1 (arquivo .pfx ou .p12)</b> do órgão — ou de um procurador com procuração eletrônica no eSocial.</p>}
              <div className="flex flex-wrap gap-2">
                {can("esocial.transmissao", "editar") && <Button size="sm" variant={c ? "outline" : "default"} onClick={() => setUploading(true)}><Upload /> {c ? "Trocar certificado" : "Enviar certificado"}</Button>}
                {c && can("esocial.transmissao", "editar") && <Button size="sm" variant="outline" onClick={test} disabled={testing}>{testing ? <Loader2 className="animate-spin" /> : <PlugZap />} Testar conexão com o eSocial</Button>}
              </div>
              <p className="text-2xs text-muted-foreground">O arquivo e a senha do certificado ficam criptografados no servidor e nunca aparecem na tela. O teste apresenta o certificado ao eSocial sem enviar nenhum evento.</p>
            </CardContent>
          </Card>
          <Card className="xl:col-span-5">
            <CardHeader><CardTitle>Prontos para transmitir</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-xs">
              {Object.entries(info.data.prontos).map(([g, n]) => <div key={g} className="flex justify-between"><span className="capitalize">{g}</span><b className="tabular">{n}</b></div>)}
              <p className="text-2xs text-muted-foreground">Cada lote leva até {info.data.limite_lote} eventos do mesmo grupo. Envie primeiro os cadastros (S-2400), depois os benefícios (S-2410) e, por último, os periódicos e o fechamento (S-1299).</p>
            </CardContent>
          </Card>
        </div>
      )}
      {info.data && c && !c.vencido && can("esocial.transmissao", "incluir") && <SendPanel limit={info.data.limite_lote} production={info.data.ambiente === 1} onSent={refresh} />}
      <Card>
        <CardHeader><CardTitle>Lotes enviados</CardTitle></CardHeader>
        {batches.error && <div className="p-4"><ErrorState error={batches.error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Enviado em</TableHead><TableHead>Grupo</TableHead><TableHead>Ambiente</TableHead><TableHead className="text-right">Eventos</TableHead><TableHead>Protocolo</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {batches.isLoading && !batches.data && <LoadingRows cols={7} />}
            {batches.data?.results.map((b) => (
              <TableRow key={b.id}>
                <TableCell>{formatDateTime(b.sent_at)}<div className="text-2xs text-muted-foreground">{b.created_by_name}</div></TableCell>
                <TableCell>{b.group_display}</TableCell>
                <TableCell className="text-xs">{b.environment_display}</TableCell>
                <TableCell className="text-right tabular">{b.total}
                  {b.status === "PROCESSADO" && <div className="text-2xs"><span className="text-success">{b.resumo.ACEITO ?? 0} aceito(s)</span> · <span className="text-critical">{b.resumo.REJEITADO ?? 0} rejeitado(s)</span></div>}</TableCell>
                <TableCell className="text-xs">{b.protocol || "—"}</TableCell>
                <TableCell><Badge variant={b.status === "PROCESSADO" ? "success" : b.status === "RECUSADO" ? "critical" : "info"}>{b.status_display}</Badge>
                  {b.response_message && <div className="mt-0.5 max-w-72 text-2xs text-muted-foreground" title={b.response_message}>{b.response_code} {b.response_message.slice(0, 120)}</div>}</TableCell>
                <TableCell className="text-right">{b.status === "PROCESSANDO" && can("esocial.transmissao", "incluir") &&
                  <Button size="sm" variant="outline" onClick={() => query(b)} disabled={querying === b.id}>{querying === b.id ? <Loader2 className="animate-spin" /> : <RefreshCw />} Buscar retorno</Button>}</TableCell>
              </TableRow>
            ))}
            {batches.data?.results.length === 0 && <EmptyRow cols={7} text="Nenhum lote enviado ainda." />}
          </TableBody>
        </Table>
        {batches.data && <Pagination page={batches.data.page} numPages={batches.data.num_pages} count={batches.data.count} onChange={setPage} />}
      </Card>
      {uploading && <UploadDialog onClose={() => setUploading(false)} onDone={refresh} />}
    </>
  );
}

function UploadDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [certPass, setCertPass] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("arquivo", file);
      fd.append("senha_certificado", certPass);
      fd.append("password", password);
      const res = await fetch("/api/backend/esocial/transmissao/certificado", { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Não foi possível instalar o certificado.");
      toast.success(`Certificado de ${body.certificado.titular} instalado.`);
      (body.avisos as string[] | undefined)?.forEach((a) => toast.warning(a, { duration: 10000 }));
      onDone();
      onClose();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4" /> Certificado digital A1</DialogTitle>
          <DialogDescription>Arquivo .pfx ou .p12 do e-CNPJ do órgão (ou do procurador). Se já houver um certificado, ele será substituído.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormField label="Arquivo do certificado" required htmlFor="cert-file"><Input id="cert-file" type="file" accept=".pfx,.p12,application/x-pkcs12" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></FormField>
          <FormField label="Senha do certificado" required htmlFor="cert-pass" hint="A senha definida quando o certificado foi emitido/exportado."><Input id="cert-pass" type="password" autoComplete="off" value={certPass} onChange={(e) => setCertPass(e.target.value)} /></FormField>
          <FormField label="Sua senha do SIST (confirmação)" required htmlFor="cert-user"><Input id="cert-user" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={send} disabled={busy || !file || !password}>{busy && <Loader2 className="animate-spin" />} Instalar certificado</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SendPanel({ limit, production, onSent }: { limit: number; production: boolean; onSent: () => void }) {
  const [group, setGroup] = useState(GROUPS[0]);
  const { data, mutate, isLoading } = useSWR<Paginated<Ev>>(`esocial/eventos${qs({ situacoes: "VALIDADO", tipos: group.types.join(","), page_size: 200 })}`, fetcher);
  const rows = useMemo(() => (data?.results ?? []).filter((e) => e.status === "VALIDADO" && group.types.includes(e.event_type)), [data, group]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else if (n.size < limit) n.add(id); return n; });
  const selectFirst = () => setPicked(new Set(rows.slice(0, limit).map((r) => r.id)));
  return (
    <Card className="mb-4">
      <CardHeader className="flex-wrap gap-2">
        <CardTitle>Enviar lote</CardTitle>
        <div className="flex flex-wrap gap-1">
          {GROUPS.map((g) => <Button key={g.n} size="sm" variant={g.n === group.n ? "default" : "outline"} onClick={() => { setGroup(g); setPicked(new Set()); }}>{g.label}</Button>)}
        </div>
      </CardHeader>
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2 text-xs">
        <Button size="sm" variant="ghost" onClick={selectFirst} disabled={!rows.length}>Selecionar os {Math.min(limit, rows.length)} primeiros</Button>
        {picked.size > 0 && <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Limpar</Button>}
        <span className="text-muted-foreground">{picked.size} de {limit} no lote</span>
        <Button size="sm" className="ml-auto" disabled={!picked.size} onClick={() => setConfirming(true)}><Send /> Transmitir {picked.size || ""} evento(s)</Button>
      </div>
      <div className="max-h-80 overflow-auto">
        <Table>
          <TableHeader><TableRow><TableHead className="w-8" /><TableHead>Evento</TableHead><TableHead>Referência</TableHead><TableHead>Período</TableHead><TableHead>Gerado em</TableHead></TableRow></TableHeader>
          <TableBody>
            {isLoading && <LoadingRows cols={5} />}
            {rows.map((e) => (
              <TableRow key={e.id} className="cursor-pointer" onClick={() => toggle(e.id)}>
                <TableCell><input type="checkbox" readOnly checked={picked.has(e.id)} aria-label="Incluir no lote" /></TableCell>
                <TableCell>{e.event_type}</TableCell><TableCell>{e.reference}</TableCell><TableCell>{e.period || "—"}</TableCell><TableCell>{formatDateTime(e.created_at)}</TableCell>
              </TableRow>
            ))}
            {data && rows.length === 0 && <EmptyRow cols={5} text="Nenhum evento pronto neste grupo. Gere e corrija as pendências nas telas do eSocial." />}
          </TableBody>
        </Table>
      </div>
      {confirming && <ConfirmSend ids={[...picked]} production={production} onClose={() => setConfirming(false)} onDone={() => { setPicked(new Set()); mutate(); onSent(); }} />}
    </Card>
  );
}

function ConfirmSend({ ids, production, onClose, onDone }: { ids: string[]; production: boolean; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      const b = await api<Batch>("esocial/transmissao/transmitir", { method: "POST", body: { ids, password } });
      if (b.status === "PROCESSANDO") toast.success(`Lote recebido pelo eSocial. Protocolo ${b.protocol}. Em alguns minutos, clique em "Buscar retorno".`);
      else toast.error(`O eSocial recusou o lote: ${b.response_code} ${b.response_message}`);
      onDone();
      onClose();
    } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Transmitir {ids.length} evento(s)</DialogTitle>
          <DialogDescription>{production
            ? "ATENÇÃO: ambiente de PRODUÇÃO. Os eventos aceitos valem como declaração oficial do órgão."
            : "Ambiente de produção restrita (testes): não vale como declaração oficial."} Os eventos serão assinados com o certificado do órgão.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <FormField label="Sua senha do SIST (assinatura eletrônica)" required htmlFor="tx-pass"><Input id="tx-pass" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></FormField>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button variant={production ? "destructive" : "default"} onClick={send} disabled={busy || !password}>{busy && <Loader2 className="animate-spin" />} Transmitir</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
