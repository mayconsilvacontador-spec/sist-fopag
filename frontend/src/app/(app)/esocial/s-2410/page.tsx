"use client";

import { EventsPage } from "@/components/esocial/esocial";

export default function Page() {
  return <EventsPage module="esocial.s2410" title="S-2410 / S-2420 — Benefícios" description="Início (S-2410) e término (S-2420) de cada benefício. Informe o tipo de benefício (Tabela 25) e o motivo do término (Tabela 26) em Folha › Beneficiários." tipos={["S-2410", "S-2420"]} generate={["cadastrais"]} />;
}
