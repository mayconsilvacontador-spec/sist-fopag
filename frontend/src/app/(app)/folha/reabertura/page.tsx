"use client";

import { RunsPage } from "@/components/folha/runs";

export default function Page() {
  return <RunsPage module="folha.reabertura" title="Reabertura" description="Folhas fechadas (ainda não pagas) podem ser reabertas com justificativa. Folha paga não reabre: corrija na folha seguinte por Diferenças." statuses={["FECHADA"]} />;
}
