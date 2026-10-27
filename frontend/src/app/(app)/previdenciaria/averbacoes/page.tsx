"use client";

import { useSession } from "@/components/providers/session-provider";
import { PersonScopedPage } from "@/components/previdencia/person-scoped-page";
import { TempoPanel } from "@/components/previdencia/tempo-panel";

export default function Page() {
  const { can } = useSession();
  return (
    <PersonScopedPage
      module="previdenciaria.averbacoes"
      title="Averbações"
      description="Tempo de contribuição de outros regimes e órgãos (INSS, outros RPPS, Forças Armadas), conforme certidão."
    >
      {(id) => <TempoPanel personId={id} canEdit={can("previdenciaria.averbacoes", "editar")} />}
    </PersonScopedPage>
  );
}
