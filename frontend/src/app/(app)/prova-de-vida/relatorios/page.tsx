import { Suspense } from "react";

import { ReportsPage } from "@/components/reports/reports-page";

export default function Page() {
  return (
    <Suspense>
      <ReportsPage module="provadevida.relatorios" title="Relatórios de Prova de Vida" description="Situação de cada campanha e resumo geral." />
    </Suspense>
  );
}
