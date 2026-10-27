"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";

import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DependencyRow } from "@/lib/types";

export default function DependentsPage() {
  return (
    <RequirePermission module="cadastros.dependentes">
      <Dependents />
    </RequirePermission>
  );
}

function Dependents() {
  const [page, setPage] = useState(1);
  const { data, error, isLoading } = useSWR<Paginated<DependencyRow>>(`dependencies${qs({ page })}`, fetcher, { keepPreviousData: true });
  return (
    <>
      <PageHeader
        title="Dependentes"
        description="Todas as relações de dependência. Para incluir, abra o titular no Cadastro Único › aba Dependentes."
        breadcrumb={[{ label: "Gestão de Cadastros" }, { label: "Dependentes" }]}
      />
      <Card>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Dependente</TableHead>
              <TableHead>Titular</TableHead>
              <TableHead>Dependência</TableHead>
              <TableHead>Período</TableHead>
              <TableHead>Situação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={5} />}
            {data?.results.map((d) => (
              <TableRow key={d.id}>
                <TableCell>
                  <Link href={`/cadastros/pessoas/${d.dependent}`} className="font-medium text-primary hover:underline">{d.dependent_data.name}</Link>
                  <div className="text-2xs text-muted-foreground">{d.dependent_data.cpf_formatado} · {d.dependent_data.idade} anos</div>
                </TableCell>
                <TableCell><Link href={`/cadastros/pessoas/${d.holder}`} className="hover:underline">{d.holder_name}</Link></TableCell>
                <TableCell>{d.kind_display}</TableCell>
                <TableCell className="text-xs">{formatDate(d.start_date)}{d.end_date ? ` a ${formatDate(d.end_date)}` : ""}</TableCell>
                <TableCell>{d.active ? <Badge variant="success">Ativa</Badge> : <Badge variant="neutral">Encerrada</Badge>}</TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={5} />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
    </>
  );
}
