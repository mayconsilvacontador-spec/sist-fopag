"use client";

import Link from "next/link";
import useSWR from "swr";
import {
  AlertTriangle, ArrowRight, Banknote, CalendarCheck, CalendarRange, ChevronRight, ClipboardList, FileText, HeartHandshake, Info,
  Minus, RefreshCw, UserCheck, Users, Wallet,
} from "lucide-react";

import { BeneficiariesChart, PayrollEvolutionChart, SplitBars } from "@/components/dashboard/charts";
import { useAppState } from "@/components/providers/app-state";
import { useSession } from "@/components/providers/session-provider";
import { ErrorState } from "@/components/shared/data-states";
import { PageHeader } from "@/components/shared/page-header";
import { PlanFilter } from "@/components/shared/plan-filter";
import { RequirePermission } from "@/components/shared/require-permission";
import { SourceBadge } from "@/components/shared/status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { formatCurrency, formatDateTime, formatInt } from "@/lib/format";
import type { Alert, Source } from "@/lib/types";
import { cn } from "@/lib/utils";

type DashboardData = {
  filtro: { plano: string; exercicio: number };
  cabecalho: {
    exercicio: { ano: number; cadastrado: boolean; situacao: string | null };
    competencia_referencia: { codigo: string; rotulo: string; situacao: string } | null;
    proxima_competencia: { codigo: string; rotulo: string } | null;
    pendencias: { total: number; criticos: number; demo: number; source: Source };
    folha: { status: string; competencia: string; source: Source; note: string };
    beneficiarios: { value: number | null; source: Source; note: string };
  };
  avisos: Alert[];
  cards: { key: string; label: string; value: number | string | null; format: "int" | "currency"; source: Source; note: string }[];
  graficos: {
    source: Source;
    note: string;
    evolucao_folha: { rotulo: string; competencia: string; bruta: string; liquida: string; descontos: string }[];
    beneficiarios: { rotulo: string; competencia: string; aposentados: number; pensionistas: number; total: number }[];
    aposentados_pensionistas: { nome: string; valor: number }[];
    por_plano: { plano: string; massa: string; beneficiarios: number; bruta: string }[];
  };
  gerado_em: string;
};

const CARD_ICONS: Record<string, typeof Users> = {
  total_beneficiarios: Users,
  aposentados: UserCheck,
  pensionistas: HeartHandshake,
  folha_bruta: Wallet,
  folha_liquida: Banknote,
  descontos: Minus,
};

export default function DashboardPage() {
  return (
    <RequirePermission module="painel">
      <Dashboard />
    </RequirePermission>
  );
}

function Dashboard() {
  const { me, can } = useSession();
  const { plan, exercise } = useAppState();
  const { data, error, isLoading, mutate, isValidating } = useSWR<DashboardData>(
    `dashboard?plano=${plan}&exercicio=${exercise}`,
    fetcher,
    { keepPreviousData: true },
  );
  const unavailable = data?.graficos.source === "indisponivel";
  const p = data?.cabecalho.pendencias;
  const ok = (s?: string | null) => /abert|paga|fechad|conferid/i.test(s ?? "");

  return (
    <>
      <PageHeader
        title="Painel Geral"
        description={me?.institution?.name}
        actions={
          <>
            <PlanFilter />
            <Button variant="outline" onClick={() => mutate()} disabled={isValidating} className="h-9">
              <RefreshCw className={cn(isValidating && "animate-spin")} /> Atualizar
            </Button>
          </>
        }
      />

      {error && <ErrorState error={error} />}

      {data && data.cards.find((c) => c.key === "folha_bruta")?.value == null && (
        <div className="mb-4 rounded-lg border border-info-border bg-info-soft px-4 py-2.5 text-xs text-info">
          Os beneficiários vêm dos benefícios implantados. Os valores da folha aparecem depois que a primeira folha mensal
          for calculada em <Link href="/folha/folha-mensal" className="font-medium underline">Folha de Benefícios › Folha Mensal</Link>.
        </div>
      )}

      {/* Resumo */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <StatCard icon={CalendarRange} label="Exercício" value={data ? String(data.cabecalho.exercicio.ano) : null}
          hint={data && (!data.cabecalho.exercicio.cadastrado ? <span className="text-warning">Não cadastrado</span>
            : <span className={cn(ok(data.cabecalho.exercicio.situacao) && "text-success")}>{data.cabecalho.exercicio.situacao}</span>)} />
        <StatCard icon={CalendarCheck} label="Competência de referência"
          value={data ? data.cabecalho.competencia_referencia?.rotulo ?? "Não definida" : null}
          hint={data?.cabecalho.competencia_referencia && (
            <span className={cn(ok(data.cabecalho.competencia_referencia.situacao) && "text-success")}>{data.cabecalho.competencia_referencia.situacao}</span>)} />
        <StatCard icon={ClipboardList} tone="warning" label="Pendências" value={p ? `${formatInt(p.total)} aviso(s)` : null}
          valueClass={p && p.criticos > 0 ? "text-critical" : undefined}
          hint={p && (p.criticos > 0 ? <span className="font-semibold text-critical">{p.criticos} crítico(s)</span>
            : p.total === 0 ? "Sem pendências" : null)} />
        <StatCard icon={FileText} label={`Folha${data ? ` ${data.cabecalho.folha.competencia}` : ""}`}
          value={data ? data.cabecalho.folha.status : null} valueClass={data && ok(data.cabecalho.folha.status) ? "text-[hsl(183_65%_30%)]" : undefined}
          hint={data && data.cabecalho.folha.source !== "real" && <SourceBadge source={data.cabecalho.folha.source} note={data.cabecalho.folha.note} />} />
        <StatCard icon={Users} label="Beneficiários"
          value={data ? (data.cabecalho.beneficiarios.value != null ? formatInt(data.cabecalho.beneficiarios.value) : "—") : null}
          hint={data && data.cabecalho.beneficiarios.source !== "real" && <SourceBadge source={data.cabecalho.beneficiarios.source} note={data.cabecalho.beneficiarios.note} />} />
      </div>

      <div className="grid gap-4 lg:grid-cols-12">
        {/* Avisos */}
        <Card className="lg:col-span-5">
          <CardHeader>
            <CardTitle>Avisos e pendências</CardTitle>
            {can("alertas") && (
              <Link href="/alertas" className="flex items-center gap-1 text-xs font-medium text-primary hover:underline">
                Ver todos <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </CardHeader>
          <CardContent className="space-y-2">
            {isLoading && Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
            {data?.avisos.map((a) => <AlertBox key={a.id} alert={a} />)}
            {data && data.avisos.length === 0 && (
              <div className="py-10 text-center text-sm text-muted-foreground">Nenhuma pendência aberta.</div>
            )}
          </CardContent>
        </Card>

        {/* Indicadores */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:col-span-7 lg:content-start">
          {(data?.cards ?? Array.from({ length: 6 }).map(() => null)).map((c, i) =>
            c ? (
              <Card key={c.key} className="flex flex-col justify-between px-4 py-3.5">
                <div className="flex items-center gap-2">
                  {(() => {
                    const Icon = CARD_ICONS[c.key] ?? Users;
                    return <Icon className="h-[18px] w-[18px] shrink-0 text-primary" />;
                  })()}
                  <span className="text-[11.5px] font-semibold uppercase tracking-[0.05em] text-muted-foreground">{c.label}</span>
                </div>
                <div className="mt-2.5 text-[24px] font-bold tracking-tight text-primary-strong tabular">
                  {c.value == null ? "—" : c.format === "currency" ? formatCurrency(c.value) : formatInt(c.value)}
                </div>
                {c.source !== "real" && <div className="mt-1"><SourceBadge source={c.source} note={c.note} /></div>}
              </Card>
            ) : (
              <Card key={i} className="px-4 py-3.5">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="mt-3 h-7 w-32" />
              </Card>
            ),
          )}
        </div>

        {/* Gráficos */}
        <ChartCard title="Evolução da folha — 12 meses" source={data?.graficos.source} note={data?.graficos.note} className="lg:col-span-8">
          {data && data.graficos.evolucao_folha.length > 0 ? (
            <PayrollEvolutionChart data={data.graficos.evolucao_folha} />
          ) : (
            <ChartPlaceholder loading={isLoading} unavailable={unavailable} />
          )}
        </ChartCard>

        <ChartCard title="Aposentados x Pensionistas" source={data?.graficos.source} note={data?.graficos.note} className="lg:col-span-4">
          {data && data.graficos.aposentados_pensionistas.length > 0 ? (
            <div className="pt-1">
              <SplitBars items={data.graficos.aposentados_pensionistas.map((d) => ({ label: d.nome, value: d.valor }))} />
            </div>
          ) : (
            <ChartPlaceholder loading={isLoading} unavailable={unavailable} />
          )}
          {data && data.graficos.por_plano.length > 0 && (
            <div className="mt-5 border-t pt-4">
              <div className="mb-3 text-[12px] font-semibold uppercase tracking-[0.05em] text-primary-strong">Por folha · beneficiários</div>
              <SplitBars items={data.graficos.por_plano.map((x) => ({ label: x.plano, value: x.beneficiarios }))} />
              <div className="mb-3 mt-5 text-[12px] font-semibold uppercase tracking-[0.05em] text-primary-strong">Por folha · folha bruta</div>
              <SplitBars format="currency" items={data.graficos.por_plano.map((x) => ({ label: x.plano, value: Number(x.bruta) }))} />
            </div>
          )}
        </ChartCard>

        <ChartCard title="Quantidade de beneficiários — 12 meses" source={data?.graficos.source} note={data?.graficos.note} className="lg:col-span-12">
          {data && data.graficos.beneficiarios.length > 0 ? (
            <BeneficiariesChart data={data.graficos.beneficiarios} />
          ) : (
            <ChartPlaceholder loading={isLoading} unavailable={unavailable} />
          )}
        </ChartCard>
      </div>

      {data && (
        <p className="mt-3 text-right text-2xs text-muted-foreground">Atualizado em {formatDateTime(data.gerado_em)}</p>
      )}
    </>
  );
}

const TONES = {
  primary: "bg-primary-soft text-primary",
  warning: "bg-warning-soft text-warning",
};

function StatCard({ icon: Icon, label, value, hint, valueClass, tone = "primary" }: {
  icon: typeof Users; label: string; value: string | null; hint?: React.ReactNode; valueClass?: string; tone?: keyof typeof TONES;
}) {
  return (
    <Card className="flex items-center gap-4 px-4 py-4">
      <span className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-lg", TONES[tone])}>
        <Icon className="h-6 w-6" />
      </span>
      <div className="min-w-0">
        <div className="truncate text-[11.5px] font-semibold uppercase tracking-[0.05em] text-muted-foreground">{label}</div>
        {value === null ? <Skeleton className="mt-1.5 h-6 w-24" />
          : <div className={cn("truncate text-[20px] font-bold leading-tight text-primary-strong", valueClass)}>{value}</div>}
        {hint && <div className="mt-0.5 text-xs font-medium text-muted-foreground">{hint}</div>}
      </div>
    </Card>
  );
}

const ALERT_TONE: Record<string, { box: string; icon: string; label: string }> = {
  CRITICO: { box: "border-critical-border bg-critical-soft", icon: "text-critical", label: "text-critical" },
  ATENCAO: { box: "border-warning-border bg-warning-soft", icon: "text-warning", label: "text-warning" },
  INFORMATIVO: { box: "border-info-border bg-info-soft", icon: "text-info", label: "text-info" },
};

function AlertBox({ alert: a }: { alert: Alert }) {
  const t = ALERT_TONE[a.severity] ?? ALERT_TONE.INFORMATIVO;
  const Icon = a.severity === "INFORMATIVO" ? Info : AlertTriangle;
  return (
    <Link href={a.link || "/alertas"} className={cn("group flex items-center gap-3 rounded-lg border px-4 py-3 hover:brightness-[0.98]", t.box)}>
      <Icon className={cn("h-5 w-5 shrink-0", t.icon)} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-semibold text-foreground">{a.title}</span>
        {a.message && <span className="block truncate text-xs text-muted-foreground">{a.message}</span>}
      </span>
      {a.is_demo && <span className="shrink-0 rounded bg-demo-soft px-1.5 text-2xs font-semibold text-demo">DEMO</span>}
      <span className={cn("shrink-0 text-[11px] font-bold uppercase tracking-wide", t.label)}>{a.severity_display}</span>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </Link>
  );
}

function ChartCard({
  title, source, note, className, children,
}: {
  title: string;
  source?: Source;
  note?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {source && <SourceBadge source={source} note={note} />}
      </CardHeader>
      <CardContent className="p-3">{children}</CardContent>
    </Card>
  );
}

function ChartPlaceholder({ loading, unavailable }: { loading: boolean; unavailable: boolean }) {
  if (loading) return <Skeleton className="h-[230px] w-full" />;
  return (
    <div className="flex h-[200px] items-center justify-center rounded-md border border-dashed text-center text-xs text-muted-foreground">
      {unavailable
        ? "Disponível a partir da implantação dos módulos de Concessão (Fase 4) e Folha (Fase 5)."
        : "Sem dados para o filtro selecionado."}
    </div>
  );
}
