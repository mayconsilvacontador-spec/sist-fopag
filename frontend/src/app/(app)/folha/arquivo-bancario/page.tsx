"use client";

import { RunsPage } from "@/components/folha/runs";

export default function Page() {
  return <RunsPage module="folha.arquivo_bancario" title="Arquivo Bancário" description="Relação de crédito das folhas fechadas, por banco (planilha). O arquivo CNAB 240 é gerado em Gestão Financeira › Pagamentos." statuses={["FECHADA", "PAGA"]} tab="credito" />;
}
