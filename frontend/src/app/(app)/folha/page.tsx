"use client";

import { RunsPage } from "@/components/folha/runs";

export default function Page() {
  return <RunsPage module="folha.painel" title="Painel da Folha" description="Todas as folhas de benefícios por competência e massa (Financeiro, Previdenciário e Compra de Vidas)." canOpen />;
}
