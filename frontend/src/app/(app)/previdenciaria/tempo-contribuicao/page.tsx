"use client";

import { useSession } from "@/components/providers/session-provider";
import { PersonScopedPage } from "@/components/previdencia/person-scoped-page";
import { TempoPanel } from "@/components/previdencia/tempo-panel";

export default function Page() {
  const { can } = useSession();
  return (
    <PersonScopedPage
      module="previdenciaria.tempo_contribuicao"
      title="Tempo de Contribuição"
      description="Apuração automática a partir dos vínculos, afastamentos e averbações — sem contagem concomitante."
    >
      {(id) => <TempoPanel personId={id} canEdit={can("previdenciaria.averbacoes", "editar")} />}
    </PersonScopedPage>
  );
}
