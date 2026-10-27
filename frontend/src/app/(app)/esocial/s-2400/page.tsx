"use client";

import { EventsPage } from "@/components/esocial/esocial";

export default function Page() {
  return <EventsPage module="esocial.s2400" title="S-2400 — Beneficiários" description="Cadastro do beneficiário (dados pessoais, endereço e dependentes), gerado a partir do Cadastro Único." tipos={["S-2400"]} generate={["cadastrais"]} />;
}
