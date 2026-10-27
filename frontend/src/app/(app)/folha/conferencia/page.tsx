"use client";

import { RunsPage } from "@/components/folha/runs";

export default function Page() {
  return <RunsPage module="folha.conferencia" title="Conferência" description="Folhas calculadas aguardando conferência: compare com o mês anterior e revise os avisos." statuses={["CALCULADA"]} tab="conferencia" />;
}
