"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { Download, Folder, FolderOpen, Loader2, Plus, Upload, UserPlus } from "lucide-react";

import { NewPersonDialog } from "@/components/people/new-person-dialog";
import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { FormDialog } from "@/components/shared/registry-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, download, fetcher, type Paginated } from "@/lib/api";
import { formatDate, formatDateTime, maskCEP } from "@/lib/format";
import { ACCOUNT_TYPE, DEPENDENCY, DOC_FOLDERS, DOC_TYPE, UF_OPTIONS } from "@/lib/options";
import type { Address, BankAccount, DependencyRow, DocumentRow } from "@/lib/types";

function Toolbar({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-1 pb-2">
      <div className="section-label">{title}</div>
      <div className="flex gap-2">{children}</div>
    </div>
  );
}

function Validity({ from, to }: { from: string; to: string | null }) {
  return (
    <span className="text-xs">
      {formatDate(from)} {to ? `a ${formatDate(to)}` : ""}
      {!to && <Badge variant="success" className="ml-2">Vigente</Badge>}
    </span>
  );
}

// ---------------------------------------------------------------------------- Endereços
export function AddressesTab({ personId, canEdit }: { personId: string; canEdit: boolean }) {
  const { data, isLoading, mutate } = useSWR<Address[]>(`addresses?person=${personId}`, fetcher);
  const [adding, setAdding] = useState(false);
  return (
    <>
      <Toolbar title="Endereços (histórico)">
        {canEdit && <Button size="sm" variant="outline" onClick={() => setAdding(true)}><Plus /> Novo endereço</Button>}
      </Toolbar>
      <Table>
        <TableHeader><TableRow><TableHead>Endereço</TableHead><TableHead>Cidade</TableHead><TableHead>CEP</TableHead><TableHead>Vigência</TableHead></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={4} rows={1} />}
          {data?.map((a) => (
            <TableRow key={a.id} className={a.is_current ? "" : "opacity-60"}>
              <TableCell>{a.street}{a.number ? `, ${a.number}` : ""}{a.complement ? ` - ${a.complement}` : ""}{a.district ? ` · ${a.district}` : ""}</TableCell>
              <TableCell>{a.city}{a.uf ? `/${a.uf}` : ""}</TableCell>
              <TableCell className="tabular">{a.cep ? maskCEP(a.cep) : "—"}</TableCell>
              <TableCell><Validity from={a.valid_from} to={a.valid_to} /></TableCell>
            </TableRow>
          ))}
          {data?.length === 0 && <EmptyRow cols={4} text="Nenhum endereço cadastrado." />}
        </TableBody>
      </Table>
      <p className="px-1 pt-2 text-2xs text-muted-foreground">Um novo endereço encerra a vigência do anterior — o histórico é preservado.</p>
      {adding && (
        <FormDialog
          title="Novo endereço"
          description="O endereço atual terá a vigência encerrada no dia anterior ao início deste."
          fields={[
            { name: "cep", label: "CEP", type: "digits", maxLength: 8 },
            { name: "valid_from", label: "Vigente a partir de", type: "date", required: true },
            { name: "street", label: "Logradouro", required: true, wide: true },
            { name: "number", label: "Número" },
            { name: "complement", label: "Complemento" },
            { name: "district", label: "Bairro" },
            { name: "city", label: "Cidade", required: true },
            { name: "city_ibge", label: "Código IBGE do município", type: "digits", maxLength: 7, hint: "7 dígitos — exigido pelo eSocial (Barra Mansa: 3300407)" },
            { name: "uf", label: "UF", type: "select", options: UF_OPTIONS },
            { name: "country", label: "País" },
          ]}
          initial={{ country: "Brasil", valid_from: new Date().toISOString().slice(0, 10) }}
          onClose={() => setAdding(false)}
          submit={async (body) => { await api("addresses", { method: "POST", body: { ...body, person: personId } }); toast.success("Endereço incluído."); mutate(); }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------- Contas bancárias
export function AccountsTab({ personId, canEdit }: { personId: string; canEdit: boolean }) {
  const { data, isLoading, mutate } = useSWR<BankAccount[]>(`bank-accounts?person=${personId}`, fetcher);
  const [adding, setAdding] = useState(false);
  return (
    <>
      <Toolbar title="Contas bancárias (histórico)">
        {canEdit && <Button size="sm" variant="outline" onClick={() => setAdding(true)}><Plus /> Nova conta</Button>}
      </Toolbar>
      <Table>
        <TableHeader><TableRow><TableHead>Banco</TableHead><TableHead>Agência</TableHead><TableHead>Conta</TableHead><TableHead>Tipo</TableHead><TableHead>Vigência</TableHead></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={5} rows={1} />}
          {data?.map((a) => (
            <TableRow key={a.id} className={a.is_current ? "" : "opacity-60"}>
              <TableCell>{a.bank_label}</TableCell>
              <TableCell className="font-mono text-xs">{a.branch}{a.branch_digit ? `-${a.branch_digit}` : ""}</TableCell>
              <TableCell className="font-mono text-xs">{a.account}{a.account_digit ? `-${a.account_digit}` : ""}</TableCell>
              <TableCell>{a.account_type_display}</TableCell>
              <TableCell><Validity from={a.valid_from} to={a.valid_to} /></TableCell>
            </TableRow>
          ))}
          {data?.length === 0 && <EmptyRow cols={5} text="Nenhuma conta cadastrada." />}
        </TableBody>
      </Table>
      {adding && (
        <FormDialog
          title="Nova conta bancária"
          description="A conta atual terá a vigência encerrada no dia anterior ao início desta."
          fields={[
            { name: "bank", label: "Banco", type: "ref", required: true, wide: true, ref: { endpoint: "banks", label: (r) => `${r.code} - ${r.name}` } },
            { name: "branch", label: "Agência", type: "digits", maxLength: 5, required: true },
            { name: "branch_digit", label: "Dígito da agência", maxLength: 1 },
            { name: "account", label: "Conta", type: "digits", maxLength: 15, required: true },
            { name: "account_digit", label: "Dígito da conta", maxLength: 2 },
            { name: "account_type", label: "Tipo", type: "select", required: true, options: ACCOUNT_TYPE },
            { name: "valid_from", label: "Vigente a partir de", type: "date", required: true },
          ]}
          initial={{ account_type: "CORRENTE", valid_from: new Date().toISOString().slice(0, 10) }}
          onClose={() => setAdding(false)}
          submit={async (body) => { await api("bank-accounts", { method: "POST", body: { ...body, person: personId } }); toast.success("Conta incluída."); mutate(); }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------- Dependentes
export function DependentsTab({ personId, canEdit }: { personId: string; canEdit: boolean }) {
  const { data, isLoading, mutate } = useSWR<Paginated<DependencyRow>>(`dependencies?holder=${personId}&page_size=100`, fetcher);
  const asDependent = useSWR<Paginated<DependencyRow>>(`dependencies?dependent=${personId}&page_size=100`, fetcher);
  const [picking, setPicking] = useState(false);
  const [dependent, setDependent] = useState<{ id: string; name: string } | null>(null);
  const [ending, setEnding] = useState<DependencyRow | null>(null);

  return (
    <>
      <Toolbar title="Dependentes deste segurado">
        {canEdit && <Button size="sm" variant="outline" onClick={() => setPicking(true)}><UserPlus /> Incluir dependente</Button>}
      </Toolbar>
      <Table>
        <TableHeader><TableRow><TableHead>Dependente</TableHead><TableHead>Dependência</TableHead><TableHead>Período</TableHead><TableHead>Pensão / IR</TableHead><TableHead className="w-24" /></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={5} rows={1} />}
          {data?.results.map((d) => (
            <TableRow key={d.id} className={d.active ? "" : "opacity-60"}>
              <TableCell>
                <Link href={`/cadastros/pessoas/${d.dependent}`} className="font-medium text-primary hover:underline">{d.dependent_data.name}</Link>
                <div className="text-2xs text-muted-foreground">{d.dependent_data.cpf_formatado} · {d.dependent_data.idade} anos</div>
              </TableCell>
              <TableCell>{d.kind_display}</TableCell>
              <TableCell className="text-xs">{formatDate(d.start_date)}{d.end_date ? ` a ${formatDate(d.end_date)}` : ""}{d.end_reason && <div className="text-2xs text-muted-foreground">{d.end_reason}</div>}</TableCell>
              <TableCell className="space-x-1">{d.pension_eligible && <Badge>Pensão</Badge>}{d.tax_dependent && <Badge variant="info">IR</Badge>}</TableCell>
              <TableCell>{canEdit && d.active && <Button size="sm" variant="ghost" onClick={() => setEnding(d)}>Encerrar</Button>}</TableCell>
            </TableRow>
          ))}
          {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum dependente." />}
        </TableBody>
      </Table>

      {asDependent.data && asDependent.data.results.length > 0 && (
        <div className="mt-4">
          <Toolbar title="É dependente de" />
          <ul className="space-y-1 px-1 text-xs">
            {asDependent.data.results.map((d) => (
              <li key={d.id}>
                <Link href={`/cadastros/pessoas/${d.holder}`} className="font-medium text-primary hover:underline">{d.holder_name}</Link>{" "}
                — {d.kind_display} {d.active ? "" : `(encerrada em ${formatDate(d.end_date)})`}
              </li>
            ))}
          </ul>
        </div>
      )}

      {picking && (
        <NewPersonDialog title="Incluir dependente" onClose={() => setPicking(false)}
          onPicked={(p) => { setPicking(false); setDependent(p); }} />
      )}
      {dependent && (
        <FormDialog
          title={`Dependência de ${dependent.name}`}
          fields={[
            { name: "kind", label: "Tipo de dependência", type: "select", required: true, options: DEPENDENCY, wide: true },
            { name: "start_date", label: "Início da dependência", type: "date", required: true },
            { name: "economic_dependency", label: "Dependência econômica comprovada", type: "checkbox" },
            { name: "pension_eligible", label: "Habilitado à pensão", type: "checkbox" },
            { name: "tax_dependent", label: "Dependente para IR", type: "checkbox" },
            { name: "notes", label: "Observações", type: "textarea" },
          ]}
          initial={{ pension_eligible: true }}
          onClose={() => setDependent(null)}
          submit={async (body) => {
            await api("dependencies", { method: "POST", body: { ...body, holder: personId, dependent: dependent.id } });
            toast.success("Dependente incluído.");
            mutate();
          }}
        />
      )}
      {ending && (
        <FormDialog
          title={`Encerrar dependência de ${ending.dependent_data.name}`}
          description="A dependência não é excluída: fica no histórico com a data e o motivo do fim."
          fields={[
            { name: "end_date", label: "Fim da dependência", type: "date", required: true },
            { name: "end_reason", label: "Motivo", required: true, hint: "Ex.: maioridade, óbito, divórcio." },
          ]}
          submitLabel="Encerrar"
          onClose={() => setEnding(null)}
          submit={async (body) => { await api(`dependencies/${ending.id}`, { method: "PATCH", body }); toast.success("Dependência encerrada."); mutate(); }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------- Documentos
export function DocumentsTab({ personId, canEdit }: { personId: string; canEdit: boolean }) {
  const { data: all, isLoading, mutate } = useSWR<DocumentRow[]>(`documents?person=${personId}`, fetcher);
  const [folder, setFolder] = useState("PESSOAIS");
  const [docType, setDocType] = useState("IDENTIDADE");
  const types = DOC_FOLDERS.find((f) => f.key === folder)!.types;
  const data = all?.filter((d) => d.pasta === folder);
  const openFolder = (key: string) => {
    setFolder(key);
    setDocType(DOC_FOLDERS.find((f) => f.key === key)!.types[0]);
  };
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) { toast.error("Selecione o arquivo."); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("person", personId);
      fd.append("doc_type", docType);
      fd.append("description", description);
      fd.append("file", file);
      const res = await fetch("/api/backend/documents", { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || Object.values(body).flat().join(" ") || "Falha no envio.");
      toast.success(`Documento enviado (versão ${body.version}).`);
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
    <>
      <div className="mb-3 flex flex-wrap gap-2">
        {DOC_FOLDERS.map((f) => {
          const n = all?.filter((d) => d.pasta === f.key && !d.superseded).length ?? 0;
          const Icon = folder === f.key ? FolderOpen : Folder;
          return (
            <button key={f.key} type="button" onClick={() => openFolder(f.key)}
              className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${folder === f.key ? "border-primary bg-primary/10 font-semibold text-primary" : "hover:bg-muted"}`}>
              <Icon className="h-4 w-4" /> {f.label} <Badge variant="neutral">{n}</Badge>
            </button>
          );
        })}
      </div>
      {canEdit && (
        <div className="mb-3 grid gap-3 rounded-md border bg-muted/40 p-3 sm:grid-cols-4">
          <FormField label="Tipo" htmlFor="doc-type">
            <Select id="doc-type" value={docType} onChange={(e) => setDocType(e.target.value)}>
              {DOC_TYPE.filter((o) => types.includes(String(o.value))).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <FormField label="Descrição" htmlFor="doc-desc">
            <Input id="doc-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </FormField>
          <FormField label="Arquivo (PDF, JPG ou PNG até 10 MB)" htmlFor="doc-file">
            <Input id="doc-file" ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" className="py-1" />
          </FormField>
          <div className="flex items-end">
            <Button onClick={upload} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Upload />} Enviar</Button>
          </div>
        </div>
      )}
      <Table>
        <TableHeader><TableRow><TableHead>Documento</TableHead><TableHead>Arquivo</TableHead><TableHead>Versão</TableHead><TableHead>Enviado</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={5} rows={1} />}
          {data?.map((d) => (
            <TableRow key={d.id} className={d.superseded ? "opacity-60" : ""}>
              <TableCell><div className="font-medium">{d.doc_type_display}</div>{d.description && <div className="text-2xs text-muted-foreground">{d.description}</div>}</TableCell>
              <TableCell className="text-xs">{d.file_name}<div className="font-mono text-2xs text-muted-foreground" title={d.sha256}>SHA-256 {d.sha256.slice(0, 12)}…</div></TableCell>
              <TableCell>v{d.version} {d.superseded ? <Badge variant="neutral">Substituído</Badge> : <Badge variant="success">Atual</Badge>}</TableCell>
              <TableCell className="text-xs">{formatDateTime(d.created_at)}<div className="text-2xs text-muted-foreground">{d.uploaded_by}</div></TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Baixar"
                  onClick={() => download(`documents/${d.id}/download`, d.file_name).catch((e) => toast.error((e as Error).message))}>
                  <Download />
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {data?.length === 0 && <EmptyRow cols={5} text="Nenhum documento nesta pasta." />}
        </TableBody>
      </Table>
      <p className="px-1 pt-2 text-2xs text-muted-foreground">Reenviar um documento do mesmo tipo cria nova versão; as anteriores são mantidas com o hash SHA-256.</p>
    </>
  );
}
