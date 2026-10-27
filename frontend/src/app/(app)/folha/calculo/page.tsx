"use client";

import { RunsPage } from "@/components/folha/runs";

export default function Page() {
  return <RunsPage module="folha.calculo" title="Cálculo" description="Folhas abertas ou calculadas: clique para calcular ou recalcular." statuses={["ABERTA", "CALCULADA"]} />;
}
