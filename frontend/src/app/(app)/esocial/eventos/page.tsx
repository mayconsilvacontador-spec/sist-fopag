import { EventsPage } from "@/components/esocial/esocial";

export default function Page() {
  // tela única: gera os eventos (cadastrais e periódicos), filtra por evento e situação (pendentes, rejeitados...),
  // exporta e importa o retorno
  return (
    <EventsPage module="esocial.eventos" title="Eventos"
      description="Gere os eventos, filtre por tipo e situação (pendências, rejeições, aguardando retorno), exporte os XMLs e importe o retorno do eSocial."
      generate={["cadastrais", "rubricas", "folha", "fechamento"]} importReturn />
  );
}
