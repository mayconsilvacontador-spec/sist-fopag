"use client";

import { RunsPage } from "@/components/folha/runs";

export default function Page() {
  return <RunsPage module="folha.relatorios" title="Relatórios da Folha" description="Escolha a folha para ver o resumo por rubrica, a conferência e a relação de crédito (com exportação para planilha)." tab="resumo" />;
}
