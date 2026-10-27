"use client";

import Link from "next/link";
import useSWR from "swr";

import { EmptyRow, LoadingRows } from "@/components/shared/data-states";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";

import type { Ficha } from "./ficha";

type Pasta = {
  contracheques: { id: string; folha: string; competencia: string; orgao: string; matricula: string; situacao: string;
    proventos: string; descontos: string; liquido: string }[] | null;
  afastamentos: { tipo: string; codigo: string; inicio: string; fim: string | null; dias: number | null; remunerado: boolean;
    conta_tempo: boolean; matricula: string; descricao: string; ato: string }[];
  beneficios: {
    beneficios: { tipo: string; inicio: string; valor: string; situacao: string; fundamento: string; instituidor: string }[];
    importados: { tipo: string; inicio: string | null; valor: string; implantado: boolean }[];
    processos: { id: string; tipo: string; etapa: string; processo: string; aberto: string | null }[];
  } | null;
};

export function usePasta(personId: string) {
  return useSWR<Pasta>(`people/${personId}/pasta`, fetcher);
}

function H({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 mt-4 text-sm font-bold text-primary-strong first:mt-0">{children}</h3>;
}

export function RemuneracaoTab({ personId, ficha, children }: { personId: string; ficha?: Ficha; children?: React.ReactNode }) {
  const { data, isLoading } = usePasta(personId);
  const v = ficha?.vinculo_ativo;
  return (
    <div>
      <H>Remuneração atual</H>
      <div className="mb-4 grid gap-3 rounded-lg bg-muted/50 p-3 sm:grid-cols-3">
        <div><div className="text-2xs text-muted-foreground">Vencimento base</div>
          <div className="font-semibold">{v?.vencimento?.valor ? formatCurrency(v.vencimento.valor) : "Não informado"}</div>
          <div className="text-2xs text-muted-foreground">{v?.vencimento?.origem}</div></div>
        <div><div className="text-2xs text-muted-foreground">Classe / nível</div><div className="font-semibold">{v?.nivel || "—"}</div></div>
        <div><div className="text-2xs text-muted-foreground">Carga horária</div>
          <div className="font-semibold">{v?.carga_horaria ? `${v.carga_horaria} h semanais` : "—"}</div></div>
      </div>
      <H>Contracheques (Folha de Ativos)</H>
      {data?.contracheques === null ? (
        <p className="text-xs text-muted-foreground">Sem permissão para ver a Folha de Ativos.</p>
      ) : (
        <Table>
          <TableHeader><TableRow><TableHead>Competência</TableHead><TableHead>Órgão</TableHead><TableHead>Situação</TableHead>
            <TableHead className="text-right">Proventos</TableHead><TableHead className="text-right">Descontos</TableHead><TableHead className="text-right">Líquido</TableHead></TableRow></TableHeader>
          <TableBody>
            {isLoading && <LoadingRows cols={6} rows={2} />}
            {data?.contracheques?.map((c) => (
              <TableRow key={c.id}>
                <TableCell><Link href={`/ativos/folhas/${c.folha}`} className="font-medium text-primary hover:underline">{c.competencia}</Link></TableCell>
                <TableCell className="text-xs">{c.orgao} · mat. {c.matricula}</TableCell>
                <TableCell>{c.situacao}</TableCell>
                <TableCell className="text-right">{formatCurrency(c.proventos)}</TableCell>
                <TableCell className="text-right">{formatCurrency(c.descontos)}</TableCell>
                <TableCell className="text-right font-semibold">{formatCurrency(c.liquido)}</TableCell>
              </TableRow>
            ))}
            {data?.contracheques?.length === 0 && <EmptyRow cols={6} text="Nenhuma folha de ativos calculada para este servidor." />}
          </TableBody>
        </Table>
      )}
      {children}
    </div>
  );
}

export function AfastamentosTab({ personId }: { personId: string }) {
  const { data, isLoading } = usePasta(personId);
  return (
    <div>
      <H>Licenças, afastamentos, faltas e cessões</H>
      <Table>
        <TableHeader><TableRow><TableHead>Tipo</TableHead><TableHead>Período</TableHead><TableHead>Dias</TableHead>
          <TableHead>Efeitos</TableHead><TableHead>Descrição / ato</TableHead></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={5} rows={2} />}
          {data?.afastamentos.map((a, i) => (
            <TableRow key={i}>
              <TableCell className="font-medium">{a.tipo}<div className="text-2xs text-muted-foreground">mat. {a.matricula}</div></TableCell>
              <TableCell className="text-xs">{formatDate(a.inicio)}{a.fim ? ` a ${formatDate(a.fim)}` : " (em aberto)"}</TableCell>
              <TableCell>{a.dias ?? "—"}</TableCell>
              <TableCell className="space-x-1">
                <Badge variant={a.remunerado ? "success" : "warning"}>{a.remunerado ? "Remunerado" : "Sem remuneração"}</Badge>
                {!a.conta_tempo && <Badge variant="neutral">Não conta tempo</Badge>}
              </TableCell>
              <TableCell className="text-xs">{a.descricao}{a.ato && <div className="text-muted-foreground">{a.ato}</div>}</TableCell>
            </TableRow>
          ))}
          {data?.afastamentos.length === 0 && <EmptyRow cols={5} text="Nenhum afastamento registrado." />}
        </TableBody>
      </Table>
      <p className="mt-2 text-2xs text-muted-foreground">
        Para lançar uma licença, afastamento ou falta, use a aba Vida Funcional (eventos do vínculo). O controle de férias
        (períodos aquisitivos e 1/3) chega na próxima etapa da Folha de Ativos.
      </p>
    </div>
  );
}

export function BeneficiosTab({ personId, children }: { personId: string; children?: React.ReactNode }) {
  const { data, isLoading } = usePasta(personId);
  const b = data?.beneficios;
  return (
    <div>
      <H>Benefícios previdenciários</H>
      <Table>
        <TableHeader><TableRow><TableHead>Benefício</TableHead><TableHead>Início</TableHead><TableHead>Valor</TableHead><TableHead>Situação</TableHead></TableRow></TableHeader>
        <TableBody>
          {isLoading && <LoadingRows cols={4} rows={1} />}
          {b?.beneficios.map((x, i) => (
            <TableRow key={i}>
              <TableCell className="font-medium">{x.tipo}{x.instituidor && <div className="text-2xs text-muted-foreground">Instituidor: {x.instituidor}</div>}
                {x.fundamento && <div className="text-2xs text-muted-foreground">{x.fundamento}</div>}</TableCell>
              <TableCell>{formatDate(x.inicio)}</TableCell>
              <TableCell>{formatCurrency(x.valor)}</TableCell>
              <TableCell>{x.situacao}</TableCell>
            </TableRow>
          ))}
          {b?.importados.map((x, i) => (
            <TableRow key={`i${i}`}>
              <TableCell className="font-medium">{x.tipo} <Badge variant="neutral">base atuarial</Badge></TableCell>
              <TableCell>{formatDate(x.inicio)}</TableCell>
              <TableCell>{x.valor ? formatCurrency(x.valor) : "—"}</TableCell>
              <TableCell>{x.implantado ? "Implantado na folha" : "Não implantado"}</TableCell>
            </TableRow>
          ))}
          {b && !b.beneficios.length && !b.importados.length && <EmptyRow cols={4} text="Nenhum benefício." />}
        </TableBody>
      </Table>
      {!!b?.processos.length && (
        <>
          <H>Processos de concessão</H>
          <ul className="space-y-1 text-sm">
            {b.processos.map((p) => (
              <li key={p.id}>
                <Link href={`/concessao/processo/${p.id}`} className="font-medium text-primary hover:underline">{p.tipo} — processo {p.processo}</Link>
                <span className="text-xs text-muted-foreground"> · aberto em {formatDate(p.aberto)} · {p.etapa}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {children}
    </div>
  );
}
