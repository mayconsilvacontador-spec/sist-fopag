import { Suspense } from "react";

import { ReportsPage } from "@/components/reports/reports-page";

export default function Page() {
  return (
    <Suspense>
      <ReportsPage module="recadastramento.pendencias" title="Pendências de Recadastramento" description="Quem ainda não fez, providências para a equipe e resumo das campanhas." />
    </Suspense>
  );
}
