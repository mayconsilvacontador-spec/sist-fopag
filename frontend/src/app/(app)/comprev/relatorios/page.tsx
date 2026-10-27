import { Suspense } from "react";

import { ReportsPage } from "@/components/reports/reports-page";

export default function Page() {
  return <Suspense><ReportsPage module="comprev.relatorios" title="Relatórios COMPREV" description="Requerimentos, fluxo previsto × realizado, recebimentos e pagamentos do ano, exigências e benefícios sem requerimento." /></Suspense>;
}
