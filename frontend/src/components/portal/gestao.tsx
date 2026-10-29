"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Copy, KeyRound, Loader2, Plus } from "lucide-react";

import { PersonPicker } from "@/components/people/person-picker";
import { useSession } from "@/components/providers/session-provider";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { FormDialog } from "@/components/shared/registry-page";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { PersonRow } from "@/lib/types";

type Access = { id: string; person: string; person_name: string; person_cpf: string; active: boolean; last_access: string | null; must_change_password: boolean; locked: boolean; created_at: string };
type Msg = { id: string; person_name: string; channel_display: string; phone: string; text: string; status: string; status_display: string; sent_at: string | null; sent_by_name: string; created_at: string; whatsapp: string };
type Req = { id: string; person_name: string; person_cpf: string; kind_display: string; subject: string; message: string; status: string; status_display: string; answer: string; answered_by_name: string; answered_at: string | null; created_at: string };

export function PortalAdminPage() {
  return <RequirePermission module="portal"><PortalAdmin /></RequirePermission>;
}

function PortalAdmin() {
  const pending = useSWR<Paginated<Req>>("portal-admin/solicitacoes?status=ABERTA&page_size=1", fetcher);
  const msgs = useSWR<Paginated<Msg>>("portal-admin/mensagens?situacao=PENDENTE&page_size=1", fetcher);
  return (
    <>
      <PageHeader title="Portal do Segurado" breadcrumb={[{ label: "Portal do Segurado" }]}
        description={<>Acessos dos segurados e solicitações recebidas. Endereço do portal para divulgar: <b><Origin />/segurado</b></>} />
      <Tabs defaultValue="acessos">
        <TabsList className="mb-3">
          <TabsTrigger value="acessos">Acessos</TabsTrigger>
          <TabsTrigger value="solicitacoes">Solicitações {pending.data?.count ? <Badge variant="warning" className="ml-1">{pending.data.count}</Badge> : null}</TabsTrigger>
          <TabsTrigger value="mensagens">Mensagens ao celular {msgs.data?.count ? <Badge variant="warning" className="ml-1">{msgs.data.count}</Badge> : null}</TabsTrigger>
        </TabsList>
        <TabsContent value="acessos" className="pt-0"><Accesses /></TabsContent>
        <TabsContent value="solicitacoes" className="pt-0"><Requests onChanged={() => pending.mutate()} /></TabsContent>
        <TabsContent value="mensagens" className="pt-0"><Messages onChanged={() => msgs.mutate()} /></TabsContent>
      </Tabs>
    </>
  );
}

function Origin() {
  const [o, setO] = useState("");
  useEffect(() => setO(window.location.origin), []);
  return <>{o}</>;
}

function Accesses() {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [issued, setIssued] = useState<{ nome: string; login: string; senha: string } | null>(null);
  const [blocking, setBlocking] = useState<Access | null>(null);
  useEffect(() => { const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300); return () => clearTimeout(t); }, [search]);
  const { data, error, mutate } = useSWR<Paginated<Access>>(`portal-admin/acessos${qs({ search: debounced, page })}`, fetcher);
  const issue = async (personId: string) => {
    const r = await api<Access & { senha_provisoria: string; login: string }>("portal-admin/acessos", { method: "POST", body: { person: personId } });
    setIssued({ nome: r.person_name, login: r.login, senha: r.senha_provisoria });
    mutate();
  };
  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2.5">
          <Input className="max-w-xs" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome ou CPF" />
          {can("portal", "editar") && <Button size="sm" onClick={() => setCreating(true)}><Plus /> Liberar acesso</Button>}
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader><TableRow><TableHead>Segurado</TableHead><TableHead>Último acesso</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={4} />}
            {data?.results.map((a) => (
              <TableRow key={a.id}>
                <TableCell><div className="font-medium">{a.person_name}</div><div className="text-2xs text-muted-foreground">{a.person_cpf}</div></TableCell>
                <TableCell className="text-xs">{a.last_access ? formatDateTime(a.last_access) : "Nunca acessou"}</TableCell>
                <TableCell>{!a.active ? <Badge variant="neutral">Bloqueado</Badge> : a.locked ? <Badge variant="critical">Travado (senha errada)</Badge>
                  : a.must_change_password ? <Badge variant="warning">Aguardando 1º acesso</Badge> : <Badge variant="success">Ativo</Badge>}</TableCell>
                <TableCell className="whitespace-nowrap">{can("portal", "editar") && <>
                  <Button size="sm" variant="ghost" onClick={() => issue(a.person).catch((e) => toast.error((e as Error).message))}><KeyRound /> Nova senha</Button>
                  {a.active && <Button size="sm" variant="ghost" onClick={() => setBlocking(a)}>Bloquear</Button>}
                </>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={4} text="Nenhum acesso liberado." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {creating && <CreateDialog onClose={() => setCreating(false)} onCreate={async (p) => { await issue(p.id); setCreating(false); }} />}
      {issued && (
        <Dialog open onOpenChange={(v) => !v && setIssued(null)}>
          <DialogContent size="sm">
            <DialogHeader>
              <DialogTitle>Senha provisória de {issued.nome}</DialogTitle>
              <DialogDescription>Entregue ao segurado de forma segura. Ela aparece <b>só agora</b>; no primeiro acesso ele cria a própria senha.</DialogDescription>
            </DialogHeader>
            <DialogBody className="space-y-2 text-sm">
              <div>Login (CPF): <b>{issued.login}</b></div>
              <div className="flex items-center gap-2">Senha: <code className="rounded bg-muted px-2 py-1 font-mono text-base">{issued.senha}</code>
                <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Copiar" onClick={() => navigator.clipboard.writeText(issued.senha).then(() => toast.success("Copiada."))}><Copy /></Button></div>
              <div className="text-xs text-muted-foreground">Endereço: {window.location.origin}/segurado</div>
            </DialogBody>
            <DialogFooter><Button onClick={() => setIssued(null)}>Concluir</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      <ConfirmDialog open={!!blocking} onOpenChange={(v) => !v && setBlocking(null)} title={`Bloquear o acesso de ${blocking?.person_name ?? ""}?`}
        requireJustification destructive confirmLabel="Bloquear"
        onConfirm={async (j) => {
          try {
            await api(`portal-admin/acessos/${blocking!.id}/deactivate`, { method: "POST", body: { justification: j } });
            toast.success("Acesso bloqueado.");
            mutate();
          } catch (err) {
            toast.error((err as Error).message);
            throw err;
          }
        }} />
    </>
  );
}

function CreateDialog({ onClose, onCreate }: { onClose: () => void; onCreate: (p: PersonRow) => Promise<void> }) {
  const [person, setPerson] = useState<PersonRow | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Liberar acesso ao portal</DialogTitle>
          <DialogDescription>Escolha a pessoa (servidor, aposentado ou pensionista). O sistema gera uma senha provisória (se o acesso já existir, gera uma nova).</DialogDescription>
        </DialogHeader>
        <DialogBody><PersonPicker value={person} onChange={setPerson} /></DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button disabled={!person || busy} onClick={async () => {
            setBusy(true);
            try { await onCreate(person!); } catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
          }}>{busy && <Loader2 className="animate-spin" />} Gerar senha provisória</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Requests({ onChanged }: { onChanged: () => void }) {
  const { can } = useSession();
  const [status, setStatus] = useState("ABERTA");
  const [page, setPage] = useState(1);
  const [answering, setAnswering] = useState<Req | null>(null);
  const { data, mutate } = useSWR<Paginated<Req>>(`portal-admin/solicitacoes${qs({ status, page })}`, fetcher);
  return (
    <>
      <Card>
        <div className="border-b px-4 py-2.5">
          <Select className="w-48" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
            <option value="ABERTA">Recebidas</option><option value="EM_ANALISE">Em análise</option><option value="RESPONDIDA">Respondidas</option><option value="">Todas</option>
          </Select>
        </div>
        <Table>
          <TableHeader><TableRow><TableHead>Segurado</TableHead><TableHead>Solicitação</TableHead><TableHead>Recebida</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {!data && <LoadingRows cols={5} />}
            {data?.results.map((r) => (
              <TableRow key={r.id}>
                <TableCell><div className="font-medium">{r.person_name}</div><div className="text-2xs text-muted-foreground">{r.person_cpf}</div></TableCell>
                <TableCell className="max-w-md text-xs"><b>{r.subject}</b> <span className="text-muted-foreground">({r.kind_display})</span><div className="whitespace-pre-wrap">{r.message}</div>
                  {r.answer && <div className="mt-1 rounded bg-muted px-2 py-1">Resposta: {r.answer} <span className="text-muted-foreground">— {r.answered_by_name}</span></div>}</TableCell>
                <TableCell className="text-xs">{formatDateTime(r.created_at)}</TableCell>
                <TableCell><Badge variant={r.status === "RESPONDIDA" ? "success" : "warning"}>{r.status_display}</Badge></TableCell>
                <TableCell>{can("portal", "editar") && r.status !== "RESPONDIDA" && <Button size="sm" variant="outline" onClick={() => setAnswering(r)}>Responder</Button>}</TableCell>
              </TableRow>
            ))}
            {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhuma solicitação." />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {answering && (
        <FormDialog title={`Responder — ${answering.person_name}`} size="md" onClose={() => setAnswering(null)}
          description={`${answering.subject}: ${answering.message}`}
          initial={{ status: "RESPONDIDA", answer: answering.answer }}
          fields={[
            { name: "status", label: "Situação", type: "select", required: true, options: [{ value: "EM_ANALISE", label: "Em análise" }, { value: "RESPONDIDA", label: "Respondida" }] },
            { name: "answer", label: "Resposta ao segurado", type: "textarea" },
          ]}
          submit={async (body) => {
            await api(`portal-admin/solicitacoes/${answering.id}/answer`, { method: "POST", body });
            toast.success("Resposta registrada — o segurado vê no portal.");
            mutate();
            onChanged();
          }} />
      )}
    </>
  );
}

/**
 * Mensagens ao celular geradas pelos avisos (prova de vida, respostas...). Sem provedor de SMS/WhatsApp contratado, a
 * equipe abre o WhatsApp com o texto pronto e confirma o envio — o sistema não marca como enviada sozinho.
 */
function Messages({ onChanged }: { onChanged: () => void }) {
  const { can } = useSession();
  const [status, setStatus] = useState("PENDENTE");
  const [page, setPage] = useState(1);
  const { data, error, isLoading, mutate } = useSWR<Paginated<Msg>>(`portal-admin/mensagens${qs({ situacao: status || undefined, page })}`, fetcher);
  const act = async (m: Msg, path: string, ok: string) => {
    try { await api(`portal-admin/mensagens/${m.id}/${path}`, { method: "POST", body: {} }); toast.success(ok); mutate(); onChanged(); }
    catch (err) { toast.error((err as Error).message); }
  };
  const fmtPhone = (p: string) => `(${p.slice(0, 2)}) ${p.slice(2, 7)}-${p.slice(7)}`;
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5 text-xs">
        <Select className="w-48" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Situação">
          <option value="PENDENTE">Aguardando envio</option><option value="ENVIADA">Enviadas</option><option value="CANCELADA">Canceladas</option><option value="">Todas</option>
        </Select>
        <span className="text-muted-foreground">Envio automático por SMS/WhatsApp depende de contratar um provedor. Até lá: clique em <b>WhatsApp</b>, envie a mensagem e depois em <b>Marcar enviada</b>.</span>
      </div>
      {error && <div className="p-4"><ErrorState error={error} /></div>}
      <Table>
        <TableHeader><TableRow><TableHead>Destinatário</TableHead><TableHead>Mensagem</TableHead><TableHead>Situação</TableHead><TableHead /></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={4} />}
          {data?.results.map((m) => (
            <TableRow key={m.id}>
              <TableCell><div className="font-medium">{m.person_name}</div><div className="text-2xs text-muted-foreground">{fmtPhone(m.phone)} · {formatDateTime(m.created_at)}</div></TableCell>
              <TableCell className="max-w-md text-xs">{m.text}</TableCell>
              <TableCell><Badge variant={m.status === "ENVIADA" ? "success" : m.status === "PENDENTE" ? "warning" : "neutral"}>{m.status_display}</Badge>
                {m.sent_at && <div className="text-2xs text-muted-foreground">{formatDateTime(m.sent_at)} · {m.sent_by_name}</div>}</TableCell>
              <TableCell className="text-right">
                {m.status === "PENDENTE" && can("portal", "editar") && (
                  <div className="flex justify-end gap-1">
                    <a href={m.whatsapp} target="_blank" rel="noreferrer"><Button size="sm" variant="outline">WhatsApp</Button></a>
                    <Button size="sm" onClick={() => act(m, "mark-sent", "Envio registrado.")}>Marcar enviada</Button>
                    <Button size="sm" variant="ghost" onClick={() => act(m, "cancel", "Mensagem cancelada.")}>Cancelar</Button>
                  </div>
                )}
              </TableCell>
            </TableRow>
          ))}
          {data?.results.length === 0 && <EmptyRow cols={4} text="Nenhuma mensagem." />}
        </TableBody>
      </Table>
      {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
    </Card>
  );
}