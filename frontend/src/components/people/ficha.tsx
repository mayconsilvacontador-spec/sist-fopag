"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { Camera, Info, Loader2, Printer, Ribbon, Trash2, UserRound, Users, Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import type { Person } from "@/lib/types";

export type LinkInfo = {
  id: string; matricula: string; cargo: string; orgao: string; lotacao: string; nivel: string; admissao: string;
  servico_publico: string; massa: string; regime: string; tipo: string; forma: string; status: string; ativo: boolean;
  carga_horaria: number | null; fim: string | null; motivo_fim: string;
  vencimento: { valor: string | null; origem: string } | null;
  nomeacao: { data: string; ato: string; data_ato: string | null; publicacao: string } | null;
  posse: { data: string } | null;
};

export type Ficha = {
  situacao: string;
  tem_foto: boolean;
  vinculos: number;
  vinculo_ativo: LinkInfo | null;
  outros_vinculos: LinkInfo[];
  beneficios_ativos: { tipo: string; valor: string }[];
  endereco: { logradouro: string; numero: string; complemento: string; bairro: string; cidade: string; uf: string; cep: string } | null;
  conta: { banco: string; agencia: string; conta: string; tipo: string } | null;
  obito: { data: string | null; certidao: string };
  pensoes: { beneficiario: string; inicio: string | null; valor: string; situacao: string }[];
};

type Evento = { data: string | null; grupo: string; titulo: string; detalhe: string; link: string };

const cep = (v: string) => (v && v.length === 8 ? `${v.slice(0, 5)}-${v.slice(5)}` : v);

/** Foto do servidor (redonda): clique para anexar ou trocar (PNG/JPG/WEBP até 5 MB). */
export function PhotoBox({ personId, hasPhoto, canEdit, onChange }: { personId: string; hasPhoto: boolean; canEdit: boolean; onChange: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [v, setV] = useState(0);

  const send = async (file: File) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`/api/backend/people/${personId}/foto`, { method: "POST", body: fd, credentials: "same-origin" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "Não foi possível enviar a foto.");
      toast.success("Foto atualizada.");
      setV((x) => x + 1);
      onChange();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  };

  const remove = async () => {
    try {
      await api(`people/${personId}/foto`, { method: "DELETE" });
      toast.success("Foto removida.");
      onChange();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <div className="relative h-20 w-20 shrink-0">
      <button type="button" disabled={!canEdit || busy} onClick={() => ref.current?.click()}
        title={canEdit ? (hasPhoto ? "Clique para trocar a foto" : "Clique para anexar a foto") : undefined}
        className="group relative flex h-full w-full items-center justify-center overflow-hidden rounded-full border bg-muted">
        {hasPhoto
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={`/api/backend/people/${personId}/foto?v=${v}`} alt="Foto do servidor" className="h-full w-full object-cover" />
          : <UserRound className="h-10 w-10 text-muted-foreground" />}
        {canEdit && (
          <span className="absolute inset-0 flex items-center justify-center bg-black/45 text-white opacity-0 transition group-hover:opacity-100">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Camera className="h-5 w-5" />}
          </span>
        )}
      </button>
      {canEdit && hasPhoto && (
        <button type="button" onClick={remove} aria-label="Remover foto"
          className="absolute -right-1 -top-1 rounded-full border bg-background p-1 text-muted-foreground hover:text-critical">
          <Trash2 className="h-3 w-3" />
        </button>
      )}
      <input ref={ref} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
        onChange={(e) => e.target.files?.[0] && send(e.target.files[0])} />
    </div>
  );
}

function situacaoColor(s: string) {
  if (s === "Ativo") return "bg-success";
  if (s.startsWith("Falecid")) return "bg-muted-foreground";
  return "bg-warning";
}

/** Cartão do topo da Pasta: foto, matrícula, nome, CPF, cargo, situação e admissão. */
export function PastaHeader({ person, ficha, canEdit, onChange }: { person: Person; ficha?: Ficha; canEdit: boolean; onChange: () => void }) {
  const v = ficha?.vinculo_ativo;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-8 gap-y-4 rounded-xl border bg-card p-5 shadow-sm">
      <div className="flex items-center gap-5">
        <PhotoBox personId={person.id} hasPhoto={!!ficha?.tem_foto} canEdit={canEdit} onChange={onChange} />
        {v && (
          <div>
            <div className="text-2xs text-muted-foreground">Matrícula</div>
            <div className="text-xl font-bold text-primary-strong">{v.matricula}</div>
          </div>
        )}
        <div>
          <div className="text-lg font-bold uppercase leading-tight text-primary-strong">{person.name || "Nome não informado"}</div>
          <div className="text-xs text-muted-foreground">CPF <span className="ml-1 text-foreground">{person.cpf_formatado}</span></div>
        </div>
      </div>
      <div className="hidden h-12 border-l lg:block" />
      <div className="min-w-[220px] flex-1">
        <div className="text-2xs text-muted-foreground">{v?.ativo === false ? "Último cargo" : "Cargo atual"}</div>
        <div className="font-semibold uppercase">{v?.cargo ?? "—"}</div>
        <div className="text-xs text-muted-foreground">{v?.orgao}</div>
      </div>
      <div>
        <div className="text-2xs text-muted-foreground">Situação</div>
        {ficha ? (
          <span className="mt-1 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold">
            <span className={`h-2 w-2 rounded-full ${situacaoColor(ficha.situacao)}`} /> {ficha.situacao}
          </span>
        ) : "…"}
      </div>
      <div>
        <div className="text-2xs text-muted-foreground">Data de admissão</div>
        <div className="mt-1 text-sm font-medium">{v ? formatDate(v.admissao) : "—"}</div>
      </div>
    </div>
  );
}

function Campo({ label, value, className = "" }: { label: string; value?: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <div className="text-2xs text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">{value || "—"}</div>
    </div>
  );
}

function Bloco({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="mb-4">
      <h3 className="mb-2 text-sm font-bold text-primary-strong">{n}. {title}</h3>
      <div className="grid gap-x-4 gap-y-3 rounded-lg bg-muted/50 p-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
    </section>
  );
}

/** Ficha de Admissão (somente leitura; editar pelos botões da aba). */
export function FichaAdmissao({ person, ficha }: { person: Person; ficha: Ficha }) {
  const ref = useRef<HTMLDivElement>(null);
  const v = ficha.vinculo_ativo;
  const e = ficha.endereco;
  const print = () => {
    const w = window.open("", "_blank", "width=900,height=1000");
    if (!w || !ref.current) return;
    w.document.write(`<html><head><title>Ficha de Admissão - ${person.name}</title><style>
      body{font-family:Arial,sans-serif;font-size:12px;color:#111;margin:24px}h2{margin:0 0 4px}h3{font-size:13px;margin:16px 0 6px}
      .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;border:1px solid #ccc;padding:8px;border-radius:6px}
      .text-2xs{font-size:10px;color:#666}.text-sm{font-size:12px;font-weight:600}.no-print{display:none}
      </style></head><body><h2>Ficha de Admissão</h2>${ref.current.innerHTML}</body></html>`);
    w.document.close();
    w.focus();
    w.print();
  };
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-base font-bold text-primary-strong">Ficha de Admissão</h2>
        <Button id="btn-print-ficha" variant="outline" size="sm" onClick={print}><Printer /> Imprimir ficha</Button>
      </div>
      <div ref={ref}>
        <Bloco n={1} title="Identificação">
          <Campo label="Nome do servidor" value={person.name} className="sm:col-span-2" />
          <Campo label="CPF" value={person.cpf_formatado} />
          <Campo label="Matrícula" value={v?.matricula} />
          <Campo label="Data de nascimento" value={formatDate(person.birth_date)} />
          <Campo label="Sexo" value={person.sex_display} />
          <Campo label="Estado civil" value={person.marital_status_display} />
          <Campo label="PIS/PASEP" value={person.pis_pasep} />
          <Campo label="Nome da mãe" value={person.mother_name} className="sm:col-span-2" />
          <Campo label="RG" value={[person.rg_number, person.rg_issuer].filter(Boolean).join(" / ")} />
          <Campo label="Escolaridade" value={person.education} />
        </Bloco>
        {v && (
          <>
            <Bloco n={2} title="Cargo e Vínculo">
              <Campo label="Órgão" value={v.orgao} className="sm:col-span-2" />
              <Campo label="Cargo" value={v.cargo} className="sm:col-span-2" />
              <Campo label="Classe / Nível" value={v.nivel} />
              <Campo label="Regime" value={v.regime} />
              <Campo label="Tipo de vínculo" value={v.tipo} />
              <Campo label="Forma de admissão" value={v.forma} />
              <Campo label="Vencimento base (R$)" value={v.vencimento?.valor ? formatCurrency(v.vencimento.valor) : ""} />
              <Campo label="Carga horária" value={v.carga_horaria ? `${v.carga_horaria} horas semanais` : ""} />
              <Campo label="Massa (fundo)" value={v.massa} />
              <Campo label="Lotação" value={v.lotacao} />
            </Bloco>
            <Bloco n={3} title="Nomeação e Posse">
              <Campo label="Nº da portaria de nomeação" value={v.nomeacao?.ato} />
              <Campo label="Data da nomeação" value={formatDate(v.nomeacao?.data ?? v.admissao)} />
              <Campo label="Data da posse" value={formatDate(v.posse?.data ?? v.admissao)} />
              <Campo label="Publicação (D.O.)" value={v.nomeacao?.publicacao} />
            </Bloco>
          </>
        )}
        <Bloco n={v ? 4 : 2} title="Endereço">
          <Campo label="Logradouro" value={e ? `${e.logradouro}${e.numero ? `, ${e.numero}` : ""}` : ""} className="sm:col-span-2" />
          <Campo label="Complemento" value={e?.complemento} className="sm:col-span-2" />
          <Campo label="Bairro" value={e?.bairro} />
          <Campo label="Cidade" value={e?.cidade} />
          <Campo label="CEP" value={e ? cep(e.cep) : ""} />
          <Campo label="UF" value={e?.uf} />
        </Bloco>
        <Bloco n={v ? 5 : 3} title="Conta para crédito">
          <Campo label="Banco" value={ficha.conta?.banco} className="sm:col-span-2" />
          <Campo label="Agência" value={ficha.conta?.agencia} />
          <Campo label="Conta" value={ficha.conta ? `${ficha.conta.conta} (${ficha.conta.tipo})` : ""} />
        </Bloco>
        {ficha.outros_vinculos.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Outros vínculos: {ficha.outros_vinculos.map((o) => `${o.cargo} (${o.matricula}, ${o.status})`).join("; ")} — veja em Vida Funcional.
          </p>
        )}
      </div>
    </div>
  );
}

/** Linha do Tempo Funcional (coluna da direita). */
export function LinhaDoTempo({ personId, ficha }: { personId: string; ficha?: Ficha }) {
  const { data } = useSWR<Evento[]>(`people/${personId}/cronologia`, fetcher);
  const events = (data ?? []).filter((e) => e.grupo !== "DOCUMENTO").slice().reverse();
  const aposentado = (data ?? []).some((e) => e.grupo === "BENEFICIO" && /aposentadoria/i.test(e.titulo));
  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <h3 className="mb-3 flex items-center gap-2 font-bold text-primary-strong"><Workflow className="h-4 w-4" /> Linha do Tempo Funcional</h3>
      {!data ? <div className="h-32 animate-pulse rounded bg-muted" /> : (
        <ol className="max-h-[520px] overflow-y-auto pr-1 thin-scroll">
          {!aposentado && !ficha?.obito.data && (
            <Item date="Em aberto" title="Aposentadoria" detail="Ainda não há registro." open />
          )}
          {events.map((e, i) => (
            <Item key={i} date={e.data ? formatDate(e.data) : "—"} first={i === 0 && (aposentado || !!ficha?.obito.data)}
              title={e.link ? <Link href={e.link} className="text-primary hover:underline">{e.titulo}</Link> : e.titulo} detail={e.detalhe} />
          ))}
        </ol>
      )}
    </div>
  );
}

function Item({ date, title, detail, first, open }: { date: string; title: React.ReactNode; detail?: string; first?: boolean; open?: boolean }) {
  return (
    <li className="relative grid grid-cols-[84px_20px_1fr] gap-2 pb-4 last:pb-0">
      <span className="pt-0.5 text-right text-xs font-medium text-muted-foreground">{date}</span>
      <span className="relative flex justify-center">
        <span className="absolute bottom-[-16px] top-4 w-px bg-border" />
        <span className={`relative mt-1 h-3 w-3 rounded-full border-2 ${first ? "border-primary bg-primary" : open ? "border-muted-foreground bg-card" : "border-primary/60 bg-card"}`} />
      </span>
      <span>
        <span className="block text-sm font-semibold">{title}</span>
        {detail && <span className="block text-xs text-muted-foreground">{detail}</span>}
      </span>
    </li>
  );
}

/** Óbito / Pensão por Morte (coluna da direita). */
export function ObitoPensao({ ficha }: { ficha?: Ficha }) {
  if (!ficha) return null;
  const morto = !!ficha.obito.data;
  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <h3 className="mb-3 flex items-center gap-2 font-bold text-primary-strong"><Ribbon className="h-4 w-4" /> Óbito / Pensão por Morte</h3>
      <div className="mb-2 grid grid-cols-2 gap-3 rounded-lg bg-muted/50 p-3">
        <div>
          <div className="text-2xs text-muted-foreground">Situação do servidor</div>
          <Badge variant="neutral" className="mt-1">{morto ? "Falecido" : "Vivo"}</Badge>
        </div>
        <Campo label="Data do óbito" value={morto ? formatDate(ficha.obito.data) : "—"} />
      </div>
      {!morto && (
        <p className="mb-2 flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          <Info className="h-3.5 w-3.5" /> Não há registro de óbito para este servidor.
        </p>
      )}
      {ficha.pensoes.length ? (
        <ul className="space-y-1 text-sm">
          {ficha.pensoes.map((p, i) => (
            <li key={i} className="rounded-lg border px-3 py-2">
              <div className="font-medium">{p.beneficiario}</div>
              <div className="text-xs text-muted-foreground">desde {formatDate(p.inicio)} · {formatCurrency(p.valor)} · {p.situacao}</div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex items-center gap-3 rounded-lg border px-3 py-3 text-xs">
          <Users className="h-6 w-6 text-muted-foreground" />
          <div>
            <div className="font-semibold">Não há pensão por morte vinculada.</div>
            <div className="text-muted-foreground">Após o registro do óbito, a pensão é concedida por processo em Concessão de Benefícios › Pensão.</div>
          </div>
        </div>
      )}
    </div>
  );
}
