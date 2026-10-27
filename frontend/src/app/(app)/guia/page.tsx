"use client";

import Link from "next/link";
import { ArrowRight, BadgeCheck, Briefcase, CalendarClock, FileText, Settings, Users, Wallet } from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent } from "@/components/ui/card";

type Passo = { texto: string; tela?: { label: string; href: string; module: string } };
type Rotina = { titulo: string; quando: string; icon: typeof Users; passos: Passo[] };

const T = (label: string, href: string, module: string) => ({ label, href, module });

const ROTINAS: Rotina[] = [
  {
    titulo: "1. Preparar o sistema", quando: "Uma vez, na implantação (e quando a lei mudar)", icon: Settings,
    passos: [
      { texto: "Confira os dados da instituição, o brasão e os planos (Financeiro / Previdenciário).", tela: T("Instituição", "/administracao/instituicao", "admin.instituicao") },
      { texto: "Abra o exercício do ano e as competências.", tela: T("Exercícios", "/administracao/exercicios", "admin.exercicios") },
      { texto: "Cadastre as alíquotas do servidor e patronal com vigência (inclusive as antigas).", tela: T("Alíquotas", "/arrecadacao/aliquotas", "arrecadacao.aliquotas") },
      { texto: "Confira as regras de aposentadoria da legislação local.", tela: T("Regras de aposentadoria", "/previdenciaria/regras", "previdenciaria.regras") },
      { texto: "Cadastre órgãos (com o código SIGFIS do TCE-RJ), cargos e lotações.", tela: T("Órgãos", "/cadastros/orgaos", "cadastros.orgaos") },
      { texto: "Confira as rubricas da folha de benefícios e da folha de ativos.", tela: T("Rubricas (benefícios)", "/folha/rubricas", "folha.rubricas") },
    ],
  },
  {
    titulo: "2. Cadastrar servidores e beneficiários", quando: "Na implantação e a cada admissão", icon: Users,
    passos: [
      { texto: "Importe a base (leiaute SPREV ou a tabela padrão de servidores do SIST) — o sistema confere antes de gravar.", tela: T("Importar", "/cadastros/importacao", "cadastros.importacao") },
      { texto: "Admissão de um servidor novo: CPF, cargo, vencimento, nomeação, posse, endereço e conta de uma vez.", tela: T("Servidores › Nova admissão", "/cadastros/admissao", "cadastros.segurados") },
      { texto: "Tudo do servidor fica na Pasta do Servidor: ficha, vida funcional, remuneração, benefícios e documentos.", tela: T("Servidores", "/cadastros/servidores", "cadastros.vinculos") },
    ],
  },
  {
    titulo: "3. Folha de servidores ativos", quando: "Todo mês, por órgão", icon: Briefcase,
    passos: [
      { texto: "Mantenha a tabela de vencimentos (cargo × nível) e lance gratificações, horas extras e descontos.", tela: T("Lançamentos", "/ativos/lancamentos", "ativos.lancamentos") },
      { texto: "Abra a folha do órgão, calcule, confira o resumo e feche.", tela: T("Folhas por órgão", "/ativos/folhas", "ativos.folha") },
      { texto: "Acompanhe a ficha financeira e a contribuição descontada × devida × repassada (Pasta › Remuneração).", tela: T("Ficha financeira", "/ativos/ficha-financeira", "ativos.ficha_financeira") },
    ],
  },
  {
    titulo: "4. Folha de aposentados e pensionistas", quando: "Todo mês, por plano", icon: Wallet,
    passos: [
      { texto: "Benefícios importados: implante na aba \"Importados aguardando implantação\".", tela: T("Beneficiários", "/folha/beneficiarios", "folha.beneficiarios") },
      { texto: "Lance diferenças, consignações e pensões alimentícias; cadastre isenções de IR por moléstia grave.", tela: T("Consignações", "/folha/consignacoes", "folha.consignacoes") },
      { texto: "Folha mensal: abrir → calcular → conferir → fechar (tudo na mesma tela; reabrir só com justificativa).", tela: T("Folha mensal", "/folha/folha-mensal", "folha.folha_mensal") },
      { texto: "Pague: gere o lote, aprove, baixe a remessa para o banco e importe o retorno.", tela: T("Pagamento da folha", "/financeiro/pagamentos", "financeiro.pagamentos") },
      { texto: "Envie ao eSocial os eventos da folha (S-1207, S-1210 e S-1299).", tela: T("eSocial › Eventos", "/esocial/eventos", "esocial.eventos") },
    ],
  },
  {
    titulo: "5. Concessão de aposentadoria ou pensão", quando: "A cada pedido", icon: BadgeCheck,
    passos: [
      { texto: "Abra o processo (Nova concessão). Se o processo veio em PDF, a Leitura inteligente digita os dados por você.", tela: T("Aposentadoria", "/concessao/aposentadoria", "concessao.aposentadoria") },
      { texto: "Benefícios: compare as regras, enquadre, calcule, anexe o checklist e envie ao Jurídico." },
      { texto: "Jurídico → Controle Interno → Presidência (assina a portaria) → publicação → Folha implanta. Cada etapa pede senha." },
      { texto: "Gere a Ficha FATIMA e o SalContr.txt dentro do processo e importe no sistema FATIMA do TCE-RJ; registre o envio e o julgamento." },
      { texto: "Pensão por morte segue o mesmo caminho a partir do óbito do servidor ou aposentado.", tela: T("Pensão por morte", "/concessao/pensao", "concessao.pensao") },
    ],
  },
  {
    titulo: "6. Rotinas do ano", quando: "Em datas próprias", icon: CalendarClock,
    passos: [
      { texto: "13º salário dos beneficiários (novembro/dezembro).", tela: T("13º salário", "/folha/decimo-terceiro", "folha.decimo_terceiro") },
      { texto: "Informe de rendimentos para o IR (fevereiro).", tela: T("Informe de rendimentos", "/folha/informe-rendimentos", "folha.informe_rendimentos") },
      { texto: "Prova de vida e recadastramento dos beneficiários.", tela: T("Prova de vida", "/prova-de-vida/campanhas", "provadevida.campanhas") },
      { texto: "Base de dados para a avaliação atuarial (leiaute SPREV).", tela: T("Base atuarial", "/atuarial/base-dados", "atuarial.base") },
    ],
  },
];

export default function GuiaPage() {
  const { can } = useSession();
  return (
    <>
      <PageHeader title="Como fazer (passo a passo)"
        description="As rotinas do sistema na ordem em que acontecem. Clique no botão de cada passo para ir direto à tela."
        breadcrumb={[{ label: "Principal" }, { label: "Como fazer" }]} />
      <div className="grid gap-4 xl:grid-cols-2">
        {ROTINAS.map((r) => {
          const Icon = r.icon;
          return (
            <Card key={r.titulo}>
              <CardContent className="p-5">
                <div className="mb-3 flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><Icon className="h-5 w-5" /></span>
                  <div>
                    <h2 className="text-base font-bold text-primary-strong">{r.titulo}</h2>
                    <p className="text-xs text-muted-foreground">{r.quando}</p>
                  </div>
                </div>
                <ol className="space-y-2.5">
                  {r.passos.map((p, i) => (
                    <li key={i} className="flex gap-3 text-sm">
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-2xs font-bold text-muted-foreground">{i + 1}</span>
                      <div className="flex-1">
                        <span>{p.texto}</span>
                        {p.tela && can(p.tela.module) && (
                          <Link href={p.tela.href} className="ml-2 inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold text-primary hover:underline">
                            {p.tela.label} <ArrowRight className="h-3 w-3" />
                          </Link>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <p className="mt-4 flex items-center gap-1 text-xs text-muted-foreground">
        <FileText className="h-3.5 w-3.5" /> Os botões só aparecem para as telas que o seu perfil pode acessar.
      </p>
    </>
  );
}
