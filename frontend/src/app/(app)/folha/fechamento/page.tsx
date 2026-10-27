"use client";

import { RunsPage } from "@/components/folha/runs";

export default function Page() {
  return <RunsPage module="folha.fechamento" title="Fechamento" description="Folhas conferidas prontas para fechar e folhas fechadas aguardando o registro do pagamento." statuses={["CONFERIDA", "FECHADA"]} />;
}
