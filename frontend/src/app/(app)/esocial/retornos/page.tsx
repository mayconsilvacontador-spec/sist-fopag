"use client";

import { EventsPage } from "@/components/esocial/esocial";

export default function Page() {
  return <EventsPage module="esocial.retornos" title="Retornos" description="Eventos exportados aguardando retorno. Importe o arquivo de retorno do lote ou informe manualmente o recibo ou a rejeição." situacoes={["EXPORTADO"]} importReturn />;
}
