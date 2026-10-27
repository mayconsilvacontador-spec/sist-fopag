"use client";

import { Suspense, use } from "react";
import { notFound } from "next/navigation";

import { ReportsPage } from "@/components/reports/reports-page";

const MODULES: Record<string, [string, string, string]> = {
  previdenciarios: ["relatorios.previdenciarios", "Relatórios Previdenciários", "Servidores, previsão de aposentadorias, averbações e certidões."],
  beneficios: ["relatorios.beneficios", "Relatórios de Benefícios", "Aposentadorias e pensões, processos de concessão e eventos."],
  folha: ["relatorios.folha", "Relatórios de Folha", "Resumo das folhas, rubricas, líquidos e retenções."],
  financeiros: ["relatorios.financeiros", "Relatórios Financeiros", "Receitas, contribuições, parcelamentos e pagamentos."],
  gerenciais: ["relatorios.gerenciais", "Relatórios Gerenciais", "Quadro por massa, prazos do Protocolo e concessões por etapa."],
  estatisticos: ["relatorios.estatisticos", "Relatórios Estatísticos", "Faixa etária, faixa de valor e perfil por cargo."],
  esocial: ["relatorios.esocial", "Relatórios do eSocial", "Eventos por situação e rejeições."],
  comprev: ["relatorios.comprev", "Relatórios COMPREV", "Requerimentos, fluxo previsto × realizado, recebimentos, pagamentos e exigências."],
};

export default function Page({ params }: { params: Promise<{ modulo: string }> }) {
  const { modulo } = use(params);
  const m = MODULES[modulo];
  if (!m) notFound();
  return <Suspense><ReportsPage module={m[0]} title={m[1]} description={m[2]} /></Suspense>;
}
