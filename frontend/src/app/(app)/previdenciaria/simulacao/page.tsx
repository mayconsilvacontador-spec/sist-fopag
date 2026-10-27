"use client";

import { PersonScopedPage } from "@/components/previdencia/person-scoped-page";
import { SimulacaoPanel } from "@/components/previdencia/simulacao-panel";

export default function Page() {
  return (
    <PersonScopedPage
      module="previdenciaria.simulacao"
      title="Simulação de Aposentadoria"
      description="Enquadramento do servidor em todas as regras (Emenda à LOM 28/2025, EC 103 e direito adquirido), datas e estimativa de proventos."
    >
      {(id) => <SimulacaoPanel personId={id} />}
    </PersonScopedPage>
  );
}
