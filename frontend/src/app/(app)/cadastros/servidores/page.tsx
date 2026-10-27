"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { Download, FileSpreadsheet, Search, Upload, UserPlus } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { download, fetcher, qs, type Paginated } from "@/lib/api";
import { formatCPF, formatDate } from "@/lib/format";
import type { EmploymentLink } from "@/lib/types";

const STATUS = [
  { value: "ATIVO", label: "Ativos" }, { value: "APOSENTADO", label: "Aposentados" },
  { value: "EXONERADO", label: "Exonerados" }, { value: "FALECIDO", label: "Falecidos" }, { value: "", label: "Todos" },
];

export default function ServidoresPage() {
  return (
    <RequirePermission module="cadastros.vinculos">
      <Servidores />
    </RequirePermission>
  );
}

function Servidores() {
  const router = useRouter();
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [status, setStatus] = useState("ATIVO");
  const [organ, setOrgan] = useState("");
  const [page, setPage] = useState(1);
  const organs = useSWR<Paginated<{ id: string; name: string }>>("organs?page_size=500", fetcher);
  useEffect(() => {
    const t = setTimeout(() => { setTerm(search.trim()); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [search]);
  const { data, error, isLoading } = useSWR<Paginated<EmploymentLink>>(
    `employment-links${qs({ search: term, status, organ, page, page_size: 25, ordering: "person__name" })}`, fetcher);

  return (
    <>
      <PageHeader title="Servidores" description="Todos os servidores do município. Clique em um servidor para abrir a Pasta Funcional."
        breadcrumb={[{ label: "Gestão de Cadastros" }, { label: "Servidores" }]}
        actions={can("cadastros.segurados", "incluir") && (
          <Button onClick={() => router.push("/cadastros/admissao")}><UserPlus /> Nova admissão</Button>
        )} />

      {can("cadastros.importacao") && (
        <Card className="mb-4">
          <CardContent className="flex flex-wrap items-center gap-4 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-soft text-primary"><FileSpreadsheet /></div>
            <div className="min-w-[240px] flex-1">
              <div className="font-semibold">Importar servidores</div>
              <div className="text-xs text-muted-foreground">
                Baixe a tabela padrão, preencha uma linha por servidor (cadastro, cargo, vencimento, nomeação, endereço e conta)
                e envie. O sistema confere tudo antes de gravar. Também aceita a base atuarial (SPREV).
              </div>
            </div>
            <Button variant="outline"
              onClick={() => download("imports/modelo-servidores", "SIST_tabela_padrao_servidores.xlsx").catch((e) => toast.error((e as Error).message))}>
              <Download /> Baixar tabela padrão
            </Button>
            {can("cadastros.importacao", "incluir") && (
              <Button onClick={() => router.push("/cadastros/importacao")}><Upload /> Enviar planilha</Button>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <div className="relative min-w-[260px] flex-1">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar por nome, CPF ou matrícula" className="pl-8" />
          </div>
          <Select value={organ} onChange={(e) => { setOrgan(e.target.value); setPage(1); }} className="w-64" aria-label="Órgão">
            <option value="">Todos os órgãos</option>
            {organs.data?.results.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="w-40" aria-label="Situação">
            {STATUS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </Select>
        </div>
        {error ? <ErrorState error={error} /> : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Matrícula</TableHead><TableHead>Servidor</TableHead><TableHead>Cargo</TableHead>
                <TableHead>Órgão</TableHead><TableHead>Admissão</TableHead><TableHead>Situação</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && <LoadingRows cols={6} rows={6} />}
              {data?.results.map((l) => (
                <TableRow key={l.id} className="cursor-pointer" onClick={() => router.push(`/cadastros/pessoas/${l.person}`)}>
                  <TableCell className="font-mono text-xs font-semibold">{l.registration}</TableCell>
                  <TableCell>
                    <Link href={`/cadastros/pessoas/${l.person}`} className="font-medium text-primary hover:underline" onClick={(e) => e.stopPropagation()}>
                      {l.person_name || "Nome não informado"}
                    </Link>
                    <div className="text-2xs text-muted-foreground">CPF {formatCPF(l.person_cpf)}</div>
                  </TableCell>
                  <TableCell>{l.position_name}{l.class_level && <div className="text-2xs text-muted-foreground">Nível {l.class_level}</div>}</TableCell>
                  <TableCell className="text-xs">{l.organ_name}</TableCell>
                  <TableCell className="text-xs">{formatDate(l.ente_start)}</TableCell>
                  <TableCell><Badge variant={l.status === "ATIVO" ? "success" : "neutral"}>{l.status_display}</Badge></TableCell>
                </TableRow>
              ))}
              {data?.results.length === 0 && <EmptyRow cols={6} text="Nenhum servidor encontrado." />}
            </TableBody>
          </Table>
        )}
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
    </>
  );
}
