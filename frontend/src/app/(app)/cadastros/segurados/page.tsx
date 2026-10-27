"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { FileUp, Landmark, Loader2, Plus, Search, UserCheck } from "lucide-react";

import { NewPersonDialog } from "@/components/people/new-person-dialog";
import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState, LoadingRows } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox, Input, Select } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher, qs, type Paginated } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { PersonRow } from "@/lib/types";

export default function PeoplePage() {
  return (
    <RequirePermission module="cadastros.segurados">
      <People />
    </RequirePermission>
  );
}

function People() {
  const router = useRouter();
  const { can, me } = useSession();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [tipo, setTipo] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [semNome, setSemNome] = useState(false);
  const [filling, setFilling] = useState(false);

  useEffect(() => {
    // Atalho vindo do alerta "pessoas sem nome" (?sem_nome=1)
    if (new URLSearchParams(window.location.search).get("sem_nome") === "1") setSemNome(true);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, error, isLoading, mutate } = useSWR<Paginated<PersonRow>>(
    `people${qs({ search: debounced, tipo, page, sem_nome: semNome ? 1 : undefined })}`, fetcher, { keepPreviousData: true },
  );

  const fillNames = async () => {
    setFilling(true);
    try {
      const r = await api<{ consultados: number; preenchidos: number; restantes: number }>("people/fill-from-receita", { method: "POST" });
      toast.success(`Receita: ${r.preenchidos} de ${r.consultados} nome(s) completado(s). Restam ${r.restantes}.`);
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setFilling(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Servidores e beneficiários"
        description="Cada pessoa (servidor, aposentado, pensionista, dependente) é cadastrada uma única vez, pelo CPF."
        breadcrumb={[{ label: "Gestão de Cadastros" }, { label: "Servidores e beneficiários" }]}
        actions={
          <>
            {can("cadastros.importacao", "incluir") && (
              <Button variant="outline" onClick={() => router.push("/cadastros/importacao")}><FileUp /> Importar</Button>
            )}
            {can("cadastros.segurados", "incluir") && <Button variant="outline" onClick={() => setCreating(true)}><Plus /> Nova pessoa (dependente etc.)</Button>}
            {can("cadastros.segurados", "incluir") && <Button onClick={() => router.push("/cadastros/admissao")}><UserCheck /> Admitir servidor</Button>}
          </>
        }
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nome, CPF ou matrícula" className="pl-8" />
          </div>
          <Select className="w-48" value={tipo} onChange={(e) => { setTipo(e.target.value); setPage(1); }} aria-label="Situação">
            <option value="">Todas as pessoas</option>
            <option value="servidor">Servidores ativos</option>
            <option value="aposentado">Aposentados</option>
            <option value="dependente">Dependentes</option>
            <option value="falecido">Falecidos</option>
          </Select>
          <label className="flex items-center gap-2 text-xs">
            <Checkbox checked={semNome} onChange={(e) => { setSemNome(e.target.checked); setPage(1); }} /> Somente sem nome
          </label>
          {semNome && me?.integracoes?.receita && can("cadastros.segurados", "editar") && (
            <Button size="sm" variant="outline" onClick={fillNames} disabled={filling}>
              {filling ? <Loader2 className="animate-spin" /> : <Landmark />} Completar nomes pela Receita (50 por vez)
            </Button>
          )}
        </div>
        {error && <div className="p-4"><ErrorState error={error} /></div>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>CPF</TableHead>
              <TableHead>Nascimento</TableHead>
              <TableHead>Sexo</TableHead>
              <TableHead>Situação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && !data && <LoadingRows cols={5} />}
            {data?.results.map((p) => (
              <TableRow key={p.id} className="cursor-pointer" onClick={() => router.push(`/cadastros/pessoas/${p.id}`)}>
                <TableCell>
                  <div className="font-medium text-primary">{p.name || <span className="italic text-warning">Nome não informado (importado)</span>}</div>
                  {p.social_name && <div className="text-2xs text-muted-foreground">Nome social: {p.social_name}</div>}
                </TableCell>
                <TableCell className="tabular">{p.cpf_formatado}</TableCell>
                <TableCell>{formatDate(p.birth_date)} <span className="text-2xs text-muted-foreground">({p.idade} anos)</span></TableCell>
                <TableCell>{p.sex_display}</TableCell>
                <TableCell>{p.situacao ? <Badge variant={p.death_date ? "neutral" : "default"}>{p.situacao}</Badge> : "—"}</TableCell>
              </TableRow>
            ))}
            {data && data.results.length === 0 && <EmptyRow cols={5} />}
          </TableBody>
        </Table>
        {data && <Pagination page={data.page} numPages={data.num_pages} count={data.count} onChange={setPage} />}
      </Card>
      {creating && (
        <NewPersonDialog onClose={() => setCreating(false)} onPicked={(p) => router.push(`/cadastros/pessoas/${p.id}`)} />
      )}
    </>
  );
}
