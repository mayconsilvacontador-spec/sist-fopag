"use client";

import { EventsPage } from "@/components/esocial/esocial";

export default function Page() {
  return <EventsPage module="esocial.pendencias" title="Pendências" description="Eventos que ainda não podem ser exportados por falta de dados. Corrija o cadastro e clique em Revalidar." situacoes={["PENDENTE"]} />;
}
