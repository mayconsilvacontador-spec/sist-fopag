"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Search } from "lucide-react";

import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher, qs, type Paginated } from "@/lib/api";
import { formatCPF, formatDate } from "@/lib/format";
import type { EmploymentLink } from "@/lib/types";

export default function LinksPage() {
  return (
    <RequirePermission module="cadastros.vinculos">
      <Links />
    </RequirePermission>
  );
}

function Links() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState("ATIVO");
  const [segment, setSegment] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const { data, error, isLoading } = useSWR<Paginated<EmploymentLink>>(
    `employment-links${qs({ search: debounced, status, segment, page })}`, fetcher, { keepPreviousData: true },
  );

  return (
    <>
      <PageHeader
        title="Vínculos"
        description="Vínculos funcionais de todos os servidores. Para incluir, abra a pessoa no Cadastro Único."
        breadcrumb={[{ label: "Gestão de Cadastros" }, { label: "Vínculos" }]}
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome, CPF, matrícula ou cargo" className="pl-8" />
          </div>
          <Select className="w-44" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Status">
            <option value="ATIVO">Ativos</option>
            <option value="APOSENTADO">Aposentados</option>
            <option value="EXONERADO">Exonerados</option>
            <option value="FALECIDO">Falecidos</option>
            <option value="">Todos</option>
          </Select>
          <Select className="w-56" value={segment} onChange={(e) => { setSegment(e.target.value); setPage(1); }} aria-label="Massa">
            <option value="">Todas as massas</option>
            <option value="FINANCEIRO">Financeiro</option>
            <option value="PREVIDENCIARIO">Previdenciário</option>
            <option value="COMPRA_VIDAS">Compra de Vidas</option>
          </Select>
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Servidor</TableHead>
              <TableHead>Matrícula</TableHead>
              <TableHead>Cargo / órgão</TableHead>
              <TableHead>Início no cargo</TableHead>
              <TableHead>Massa</TableHead>
              <TableHead>Situação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={6} />}
            {data?.results.map((l) => (
              <TableRow key={l.id} className="cursor-pointer" onClick={() => router.push(`/cadastros/pessoas/${l.person}`)}>
                <TableCell><div className="font-medium text-primary">{l.person_name}</div><div className="text-2xs text-muted-foreground">{formatCPF(l.person_cpf)}</div></TableCell>
                <TableCell className="font-mono text-xs">{l.registration}</TableCell>
                <TableCell>{l.position_name}<div className="text-2xs text-muted-foreground">{l.organ_name}</div></TableCell>
                <TableCell>{formatDate(l.position_start)}</TableCell>
                <TableCell><Badge variant={l.segment === "FINANCEIRO" ? "info" : "default"}>{l.segment_display}</Badge></TableCell>
                <TableCell>{l.status === "ATIVO" ? l.situation_display : `${l.status_display} em ${formatDate(l.end_date)}`}</TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={6} />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
    </>
  );
}
