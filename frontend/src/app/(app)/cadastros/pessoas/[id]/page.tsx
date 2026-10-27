"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import {
  Briefcase, CalendarOff, ChevronDown, DollarSign, FileText, FolderOpen, HeartHandshake, Pencil, Printer, UserPlus, Users,
} from "lucide-react";

import { ContribuicoesPanel, FichaFinanceira } from "@/components/ativos/ficha";
import { FichaAdmissao, type Ficha, LinhaDoTempo, ObitoPensao, PastaHeader } from "@/components/people/ficha";
import { LinksTab } from "@/components/people/links-tab";
import { AfastamentosTab, BeneficiosTab, RemuneracaoTab } from "@/components/people/pasta-tabs";
import { PersonForm } from "@/components/people/person-form";
import { AccountsTab, AddressesTab, DependentsTab, DocumentsTab } from "@/components/people/person-tabs";
import { SalariosPanel } from "@/components/previdencia/salarios-panel";
import { SimulacaoPanel } from "@/components/previdencia/simulacao-panel";
import { TempoPanel } from "@/components/previdencia/tempo-panel";
import { useSession } from "@/components/providers/session-provider";
import { EmptyRow, ErrorState } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetcher, type Paginated } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Person, ProcessRow } from "@/lib/types";

export default function PersonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequirePermission module="cadastros.segurados">
      <PersonDetail id={id} />
    </RequirePermission>
  );
}

function PersonDetail({ id }: { id: string }) {
  const router = useRouter();
  const { can } = useSession();
  const { data: p, error, mutate } = useSWR<Person>(`people/${id}`, fetcher);
  const ficha = useSWR<Ficha>(`people/${id}/ficha`, fetcher);
  const [tab, setTab] = useState("ficha");
  const [editing, setEditing] = useState(false);
  const canEdit = can("cadastros.segurados", "editar");

  if (error) return <ErrorState error={error} />;
  if (!p) return <div className="h-64 animate-pulse rounded-lg bg-muted" />;
  const refresh = () => { mutate(); ficha.mutate(); };
  const go = (t: string) => () => setTab(t);

  return (
    <>
      <PageHeader title="Pasta do Servidor" description="Consulte os dados funcionais, históricos e vínculos do servidor."
        breadcrumb={[{ label: "Gestão de Cadastros" }, { label: "Servidores", href: "/cadastros/servidores" }, { label: "Pasta do Servidor" }]}
        actions={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">Ações <ChevronDown /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              {canEdit && <DropdownMenuItem onSelect={() => { setTab("ficha"); setEditing(true); }}><Pencil /> Editar dados pessoais</DropdownMenuItem>}
              {can("cadastros.segurados", "incluir") && (
                <DropdownMenuItem onSelect={() => router.push("/cadastros/admissao")}><UserPlus /> Nova admissão (outro vínculo)</DropdownMenuItem>
              )}
              {can("cadastros.vinculos") && <DropdownMenuItem onSelect={go("vida")}><Briefcase /> Lançar evento funcional</DropdownMenuItem>}
              <DropdownMenuItem onSelect={go("documentos")}><FolderOpen /> Anexar documento</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => { setTab("ficha"); setEditing(false); setTimeout(() => document.getElementById("btn-print-ficha")?.click(), 50); }}>
                <Printer /> Imprimir ficha
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        } />
      <PastaHeader person={p} ficha={ficha.data} canEdit={canEdit} onChange={refresh} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-4 overflow-x-auto">
          <TabsTrigger value="ficha"><FileText className="h-4 w-4" /> Ficha de Admissão</TabsTrigger>
          {can("cadastros.vinculos") && <TabsTrigger value="vida"><Briefcase className="h-4 w-4" /> Vida Funcional</TabsTrigger>}
          <TabsTrigger value="remuneracao"><DollarSign className="h-4 w-4" /> Remuneração</TabsTrigger>
          <TabsTrigger value="afastamentos"><CalendarOff className="h-4 w-4" /> Férias e Afastamentos</TabsTrigger>
          <TabsTrigger value="beneficios"><HeartHandshake className="h-4 w-4" /> Benefícios</TabsTrigger>
          {can("cadastros.dependentes") && <TabsTrigger value="dependentes"><Users className="h-4 w-4" /> Dependentes</TabsTrigger>}
          {can("protocolo.processos") && <TabsTrigger value="processos"><FolderOpen className="h-4 w-4" /> Processos</TabsTrigger>}
          <TabsTrigger value="documentos"><FileText className="h-4 w-4" /> Documentos</TabsTrigger>
        </TabsList>

        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
          <div className="min-w-0 rounded-xl border bg-card p-5 shadow-sm">
            <TabsContent value="ficha" className="mt-0">
              {editing ? (
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <h2 className="text-base font-bold text-primary-strong">Editar dados pessoais</h2>
                    <Button variant="outline" size="sm" onClick={() => setEditing(false)}>Voltar à ficha</Button>
                  </div>
                  <PersonForm key={p.updated_at} person={p} disabled={!canEdit} onSaved={() => { refresh(); setEditing(false); }} />
                  <Section title="Endereços"><AddressesTab personId={id} canEdit={canEdit} /></Section>
                  <Section title="Contas bancárias"><AccountsTab personId={id} canEdit={canEdit} /></Section>
                </div>
              ) : ficha.data ? (
                <>
                  <FichaAdmissao person={p} ficha={ficha.data} />
                  {canEdit && (
                    <Button variant="outline" size="sm" onClick={() => setEditing(true)}><Pencil /> Editar dados pessoais, endereço e conta</Button>
                  )}
                </>
              ) : <div className="h-64 animate-pulse rounded bg-muted" />}
            </TabsContent>
            <TabsContent value="vida" className="mt-0">
              <p className="mb-3 text-xs text-muted-foreground">
                Cada vínculo guarda o cargo, o vencimento e os eventos da vida funcional (nomeação, posse, progressões, lotação,
                licenças, faltas, cessões, aposentadoria, falecimento). Clique na seta do vínculo para ver e lançar eventos.
              </p>
              <LinksTab personId={id} canEdit={can("cadastros.vinculos", "editar")} canCreate={can("cadastros.vinculos", "incluir")} />
            </TabsContent>
            <TabsContent value="remuneracao" className="mt-0">
              <RemuneracaoTab personId={id} ficha={ficha.data}>
                {can("ativos.ficha_financeira") && (
                  <>
                    <Section title="Contribuição previdenciária do servidor (descontado × devido × repasse)">
                      <ContribuicoesPanel personId={id} />
                    </Section>
                    <Section title="Ficha financeira">
                      <FichaFinanceira personId={id} />
                    </Section>
                  </>
                )}
                {can("previdenciaria.historico_contributivo") && (
                  <Section title="Salários de contribuição (histórico contributivo)">
                    <SalariosPanel personId={id} canEdit={can("previdenciaria.historico_contributivo", "incluir")}
                      canExport={can("previdenciaria.historico_contributivo", "exportar")} />
                  </Section>
                )}
              </RemuneracaoTab>
            </TabsContent>
            <TabsContent value="afastamentos" className="mt-0"><AfastamentosTab personId={id} /></TabsContent>
            <TabsContent value="beneficios" className="mt-0">
              <BeneficiosTab personId={id}>
                {can("previdenciaria.tempo_contribuicao") && (
                  <Section title="Tempo de contribuição e averbações"><TempoPanel personId={id} canEdit={can("previdenciaria.averbacoes", "editar")} /></Section>
                )}
                {can("previdenciaria.simulacao") && <Section title="Simulação de aposentadoria"><SimulacaoPanel personId={id} /></Section>}
              </BeneficiosTab>
            </TabsContent>
            <TabsContent value="dependentes" className="mt-0">
              <DependentsTab personId={id} canEdit={can("cadastros.dependentes", "incluir")} />
            </TabsContent>
            <TabsContent value="processos" className="mt-0"><PersonProcesses personId={id} /></TabsContent>
            <TabsContent value="documentos" className="mt-0"><DocumentsTab personId={id} canEdit={canEdit} /></TabsContent>
          </div>
          <div className="space-y-4">
            <LinhaDoTempo personId={id} ficha={ficha.data} />
            <ObitoPensao ficha={ficha.data} />
          </div>
        </div>
      </Tabs>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="mb-2 border-b pb-1 text-sm font-bold text-primary-strong">{title}</h3>
      {children}
    </section>
  );
}

function PersonProcesses({ personId }: { personId: string }) {
  const { data } = useSWR<Paginated<ProcessRow>>(`protocol/processes?interested=${personId}&page_size=50`, fetcher);
  return (
    <Table>
      <TableHeader><TableRow><TableHead>Processo</TableHead><TableHead>Assunto</TableHead><TableHead>Situação</TableHead><TableHead>Setor</TableHead><TableHead>Vencimento</TableHead></TableRow></TableHeader>
      <TableBody>
        {data?.results.map((pr) => (
          <TableRow key={pr.id}>
            <TableCell><Link href={`/protocolo/processos/${pr.id}`} className="font-mono text-xs font-semibold text-primary hover:underline">{pr.code}</Link></TableCell>
            <TableCell>{pr.subject}<div className="text-2xs text-muted-foreground">{pr.process_type_name}</div></TableCell>
            <TableCell>{pr.status_display}</TableCell>
            <TableCell>{pr.current_sector_code}</TableCell>
            <TableCell>{formatDate(pr.due_date)}</TableCell>
          </TableRow>
        ))}
        {data?.results.length === 0 && <EmptyRow cols={5} text="Nenhum processo deste interessado." />}
      </TableBody>
    </Table>
  );
}
