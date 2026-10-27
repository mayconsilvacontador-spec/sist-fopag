"use client";

import { EventsPage } from "@/components/esocial/esocial";

export default function Page() {
  return <EventsPage module="esocial.rejeicoes" title="Rejeições" description="Eventos rejeitados pelo eSocial. Corrija o cadastro e gere o evento corrigido." situacoes={["REJEITADO"]} />;
}
