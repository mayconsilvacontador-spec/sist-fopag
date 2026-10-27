"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Construction, FileQuestion } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { PageHeader } from "@/components/shared/page-header";
import { RequirePermission } from "@/components/shared/require-permission";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { findScreenByPath } from "@/lib/menu";

const PHASES: Record<number, string> = {
  1: "Arquitetura, acesso, permissões e painel",
  2: "Cadastro Único, dependentes, vínculos, histórico funcional e documentos",
  3: "Gestão Previdenciária, histórico contributivo, CTC, regras e simulações",
  4: "Concessão de Benefícios",
  5: "Motor de Folha",
  6: "eSocial RPPS",
  7: "Financeiro, bancos e contabilidade",
  8: "Portal do Segurado",
};

/**
 * Página exibida para qualquer tela do menu ainda não implementada.
 * Nunca simula funcionalidade: informa claramente a situação e a fase.
 */
export default function InDevelopmentPage() {
  const pathname = usePathname();
  const screen = findScreenByPath(pathname);
  const { moduleInfo } = useSession();

  if (!screen) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-6 text-center">
        <FileQuestion className="mx-auto h-8 w-8 text-muted-foreground" />
        <h2 className="mt-2 text-sm font-semibold">Página não encontrada</h2>
        <p className="mt-1 text-xs text-muted-foreground">O endereço acessado não corresponde a nenhuma tela do SIST FOPAG.</p>
        <Link href="/" className="mt-3 inline-block text-xs font-medium text-primary hover:underline">Voltar ao Painel Geral</Link>
      </Card>
    );
  }

  const info = moduleInfo(screen.module);
  const phase = info?.phase ?? null;

  return (
    <RequirePermission module={screen.module}>
      <PageHeader title={screen.label} breadcrumb={[{ label: screen.group }, { label: screen.label }]} />
      <Card className="max-w-3xl p-6">
        <div className="flex items-start gap-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-warning-soft text-warning">
            <Construction className="h-5 w-5" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold">Em desenvolvimento</h2>
              <Badge variant="warning">{phase ? `Fase ${phase}` : "Fase a definir"}</Badge>
            </div>
            <p className="mt-1 text-[13px] text-muted-foreground">
              Esta tela ainda não possui funcionalidade implementada. Nenhum dado é exibido ou simulado aqui.
            </p>
            {phase && (
              <p className="mt-3 text-[13px]">
                Previsão de entrega na <strong>Fase {phase}</strong> — {PHASES[phase]}.
              </p>
            )}
            <dl className="mt-4 grid grid-cols-[140px_1fr] gap-y-1.5 text-xs">
              <dt className="text-muted-foreground">Módulo</dt>
              <dd>{screen.group}</dd>
              <dt className="text-muted-foreground">Código de permissão</dt>
              <dd><code className="rounded bg-muted px-1">{screen.module}</code></dd>
              <dt className="text-muted-foreground">Ações previstas</dt>
              <dd className="flex flex-wrap gap-1">
                {(info?.actions ?? []).map((a) => (
                  <Badge key={a} variant="neutral">{a}</Badge>
                ))}
              </dd>
            </dl>
          </div>
        </div>
      </Card>
    </RequirePermission>
  );
}
