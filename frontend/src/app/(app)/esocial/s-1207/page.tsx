"use client";

import { EventsPage } from "@/components/esocial/esocial";

export default function Page() {
  return <EventsPage module="esocial.s1207" title="S-1207 — Folha de benefícios" description="Eventos periódicos: rubricas (S-1010), benefícios pagos na folha (S-1207), pagamentos (S-1210) e fechamento do período (S-1299)." tipos={["S-1010", "S-1207", "S-1210", "S-1299"]} generate={["rubricas", "folha", "fechamento"]} />;
}
