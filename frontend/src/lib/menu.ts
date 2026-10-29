/**
 * Estrutura do menu principal do SIST.
 * `module` é o código do módulo no RBAC (catálogo do backend). Um item só é
 * exibido se o usuário tiver a permissão `<module>:visualizar`.
 * Fase e situação (implementado / em desenvolvimento) vêm do backend.
 */
import {
  ArrowLeftRight, BadgeCheck, Banknote, BarChart3, Briefcase, Calculator, ClipboardCheck,
  FileSearch, Fingerprint, FolderOpen, Landmark, LayoutDashboard, type LucideIcon, Send, Settings,
  ShieldCheck, UserRound, Users, Wallet,
} from "lucide-react";

export type MenuLeaf = {
  label: string;
  href: string;
  module: string;
  /** Título pequeno exibido ANTES deste item no menu (separa "Rotina", "Tabelas"...). */
  section?: string;
  /** Fora do menu (tela repetida ou de atalho), mas encontrada pela pesquisa global e pelos links. */
  hidden?: boolean;
};
export type MenuGroup = {
  key: string;
  label: string;
  icon: LucideIcon;
  href?: string;
  module?: string;
  items?: MenuLeaf[];
};

const L = (label: string, href: string, module: string, extra: Partial<MenuLeaf> = {}): MenuLeaf => ({ label, href, module, ...extra });
const H = (label: string, href: string, module: string): MenuLeaf => L(label, href, module, { hidden: true });

export const MENU: MenuGroup[] = [
  {
    key: "principal", label: "Principal", icon: LayoutDashboard,
    items: [
      L("Painel Geral", "/", "painel"),
      L("Como fazer (passo a passo)", "/guia", "painel"),
      L("Central de Alertas", "/alertas", "alertas"),
      L("Calendário", "/calendario", "calendario"),
    ],
  },
  {
    key: "protocolo", label: "Protocolo", icon: FolderOpen,
    items: [
      L("Processos", "/protocolo", "protocolo.processos"),
      L("Configuração", "/protocolo/configuracao", "protocolo.configuracao"),
    ],
  },
  {
    key: "cadastros", label: "Cadastros", icon: Users,
    items: [
      // a admissão, os vínculos e o histórico funcional ficam em Servidores › Pasta do Servidor
      L("Servidores", "/cadastros/servidores", "cadastros.vinculos", { section: "Pessoas" }),
      L("Dependentes", "/cadastros/dependentes", "cadastros.dependentes"),
      L("Importar servidores e beneficiários", "/cadastros/importacao", "cadastros.importacao"),
      L("Órgãos", "/cadastros/orgaos", "cadastros.orgaos", { section: "Estrutura do ente" }),
      L("Cargos", "/cadastros/cargos", "cadastros.cargos"),
      L("Lotação", "/cadastros/lotacao", "cadastros.lotacao"),
      L("Entes", "/cadastros/entes", "cadastros.entes"),
      L("Bancos", "/cadastros/bancos", "cadastros.bancos", { section: "Bancos" }),
      L("Agências", "/cadastros/agencias", "cadastros.agencias"),
      H("Vínculos", "/cadastros/vinculos", "cadastros.vinculos"),
      H("Servidores e beneficiários (todas as pessoas)", "/cadastros/segurados", "cadastros.segurados"),
      H("Admissão", "/cadastros/admissao", "cadastros.segurados"),
    ],
  },
  {
    key: "previdenciaria", label: "Gestão Previdenciária", icon: FileSearch,
    items: [
      // tempo de contribuição e averbações também ficam na Pasta do Servidor › Benefícios
      L("Simulação de aposentadoria", "/previdenciaria/simulacao", "previdenciaria.simulacao"),
      L("Histórico contributivo", "/previdenciaria/historico-contributivo", "previdenciaria.historico_contributivo"),
      L("Tempo de contribuição e averbações", "/previdenciaria/tempo-contribuicao", "previdenciaria.tempo_contribuicao"),
      L("CTC (certidões emitidas)", "/previdenciaria/ctc", "previdenciaria.ctc"),
      L("Legislação do RPPS", "/previdenciaria/legislacao", "previdenciaria.regras", { section: "Legislação e regras" }),
      L("Regras de aposentadoria", "/previdenciaria/regras", "previdenciaria.regras"),
      H("Averbações", "/previdenciaria/averbacoes", "previdenciaria.averbacoes"),
    ],
  },
  {
    key: "concessao", label: "Concessão de Benefícios", icon: BadgeCheck,
    items: [
      L("Aposentadoria", "/concessao/aposentadoria", "concessao.aposentadoria", { section: "Processos" }),
      L("Pensão por morte", "/concessao/pensao", "concessao.pensao"),
      L("Revisão de benefício", "/concessao/revisao", "concessao.revisao"),
      L("Leitura inteligente de documentos", "/concessao/leitura", "concessao.leitura"),
      L("Suspender, cessar ou reverter", "/concessao/beneficios", "concessao.suspensao", { section: "Benefícios concedidos" }),
      L("Modelos de documentos", "/concessao/modelos", "concessao.modelos", { section: "Tabelas" }),
      L("Checklist de documentos", "/concessao/checklist", "concessao.modelos"),
      H("Processos de concessão (todos)", "/concessao/processos", "concessao.processos"),
      H("Suspensão de benefícios", "/concessao/suspensao", "concessao.suspensao"),
      H("Cessação de benefícios", "/concessao/cessacao", "concessao.cessacao"),
      H("Reversão de benefícios", "/concessao/reversao", "concessao.reversao"),
    ],
  },
  {
    key: "folha", label: "Folha de Benefícios", icon: Wallet,
    items: [
      // a Folha Mensal faz o ciclo inteiro: abrir → calcular → conferir → fechar → pagar (e reabrir)
      L("Folha mensal", "/folha/folha-mensal", "folha.folha_mensal", { section: "Rotina do mês" }),
      L("13º salário", "/folha/decimo-terceiro", "folha.decimo_terceiro"),
      L("Contracheques", "/folha/contracheques", "folha.contracheques"),
      L("Informe de rendimentos (IR)", "/folha/informe-rendimentos", "folha.informe_rendimentos"),
      L("Beneficiários", "/folha/beneficiarios", "folha.beneficiarios", { section: "Beneficiários e lançamentos" }),
      L("Diferenças e descontos avulsos", "/folha/diferencas", "folha.diferencas"),
      L("Retroativos", "/folha/retroativos", "folha.retroativos"),
      L("Consignações (empréstimos)", "/folha/consignacoes", "folha.consignacoes"),
      L("Pensão alimentícia", "/folha/pensao-alimenticia", "folha.pensao_alimenticia"),
      L("Rubricas", "/folha/rubricas", "folha.rubricas", { section: "Tabelas" }),
      L("Consignatárias", "/folha/consignatarias", "folha.consignacoes"),
      L("Isenção de IR (moléstia grave)", "/folha/isencoes-ir", "folha.beneficiarios"),
      H("Painel da Folha", "/folha", "folha.painel"),
      H("Cálculo da folha", "/folha/calculo", "folha.calculo"),
      H("Conferência da folha", "/folha/conferencia", "folha.conferencia"),
      H("Fechamento da folha", "/folha/fechamento", "folha.fechamento"),
      H("Reabertura da folha", "/folha/reabertura", "folha.reabertura"),
      H("Arquivo bancário da folha", "/folha/arquivo-bancario", "folha.arquivo_bancario"),
      H("Relatórios da folha", "/folha/relatorios", "folha.relatorios"),
    ],
  },
  {
    key: "ativos", label: "Folha de Ativos", icon: Briefcase,
    items: [
      L("Folhas por órgão", "/ativos/folhas", "ativos.folha", { section: "Rotina do mês" }),
      L("Lançamentos", "/ativos/lancamentos", "ativos.lancamentos"),
      L("Ficha financeira", "/ativos/ficha-financeira", "ativos.ficha_financeira"),
      L("Tabela de vencimentos", "/ativos/vencimentos", "ativos.vencimentos", { section: "Tabelas" }),
      L("Rubricas", "/ativos/rubricas", "ativos.rubricas"),
    ],
  },
  {
    key: "esocial", label: "eSocial RPPS", icon: Send,
    items: [
      L("Painel", "/esocial", "esocial.painel"),
      L("Eventos (gerar, conferir, exportar, retorno)", "/esocial/eventos", "esocial.eventos"),
      L("Transmissão", "/esocial/transmissao", "esocial.transmissao"),
      L("Histórico de envios", "/esocial/historico", "esocial.historico"),
      H("S-2400 — Beneficiários", "/esocial/s-2400", "esocial.s2400"),
      H("S-2410 / S-2420 — Benefícios", "/esocial/s-2410", "esocial.s2410"),
      H("S-1207 — Folha de benefícios", "/esocial/s-1207", "esocial.s1207"),
      H("Retornos do eSocial", "/esocial/retornos", "esocial.retornos"),
      H("Rejeições do eSocial", "/esocial/rejeicoes", "esocial.rejeicoes"),
      H("Pendências do eSocial", "/esocial/pendencias", "esocial.pendencias"),
    ],
  },
  {
    key: "arrecadacao", label: "Arrecadação", icon: Landmark,
    items: [
      L("Contribuição do servidor", "/arrecadacao/servidor", "arrecadacao.servidor", { section: "Contribuições" }),
      L("Contribuição patronal", "/arrecadacao/patronal", "arrecadacao.patronal"),
      L("Aportes", "/arrecadacao/aportes", "arrecadacao.aportes"),
      L("Parcelamentos", "/arrecadacao/parcelamentos", "arrecadacao.parcelamentos"),
      L("Receitas recebidas", "/arrecadacao/receitas", "arrecadacao.receitas", { section: "Recebimentos" }),
      L("Conciliação das receitas", "/arrecadacao/conciliacao", "arrecadacao.conciliacao"),
      L("Divergências", "/arrecadacao/divergencias", "arrecadacao.divergencias"),
      L("Alíquotas", "/arrecadacao/aliquotas", "arrecadacao.aliquotas", { section: "Tabelas" }),
    ],
  },
  {
    key: "comprev", label: "COMPREV", icon: ArrowLeftRight,
    items: [
      L("Processos", "/comprev/processos", "comprev.processos"),
      L("Recebimentos", "/comprev/recebimentos", "comprev.recebimentos"),
      L("Pagamentos", "/comprev/pagamentos", "comprev.pagamentos"),
      L("Fluxo mensal", "/comprev/fluxo", "comprev.fluxo"),
      L("Indicadores", "/comprev/indicadores", "comprev.indicadores"),
      L("Relatórios", "/comprev/relatorios", "comprev.relatorios"),
    ],
  },
  {
    key: "recadastramento", label: "Recadastramento", icon: ClipboardCheck,
    items: [
      L("Campanhas", "/recadastramento/campanhas", "recadastramento.campanhas"),
      L("Servidores", "/recadastramento/segurados", "recadastramento.segurados"),
      L("Beneficiários", "/recadastramento/beneficiarios", "recadastramento.beneficiarios"),
      L("Pendências para a equipe", "/recadastramento/pendencias", "recadastramento.pendencias"),
    ],
  },
  {
    key: "provadevida", label: "Prova de Vida", icon: Fingerprint,
    items: [
      L("Campanhas", "/prova-de-vida/campanhas", "provadevida.campanhas"),
      L("Pendentes", "/prova-de-vida/pendentes", "provadevida.pendentes"),
      L("Realizadas", "/prova-de-vida/realizadas", "provadevida.realizadas"),
      L("Bloqueados", "/prova-de-vida/bloqueados", "provadevida.bloqueados"),
      L("Relatórios", "/prova-de-vida/relatorios", "provadevida.relatorios"),
    ],
  },
  {
    key: "financeiro", label: "Gestão Financeira", icon: Banknote,
    items: [
      L("Pagamento da folha (lotes)", "/financeiro/pagamentos", "financeiro.pagamentos"),
      L("Arquivos bancários", "/financeiro/arquivos-bancarios", "financeiro.arquivos_bancarios"),
      L("Conciliação bancária (extrato)", "/financeiro/conciliacao", "financeiro.conciliacao"),
      L("Integração contábil", "/financeiro/integracao-contabil", "financeiro.integracao_contabil"),
      L("Contas da instituição", "/financeiro/bancos", "financeiro.bancos", { section: "Tabelas" }),
    ],
  },
  {
    key: "atuarial", label: "Avaliação Atuarial", icon: Calculator,
    items: [
      L("Base de dados (SPREV)", "/atuarial/base-dados", "atuarial.base"),
    ],
  },
  {
    key: "relatorios", label: "Relatórios", icon: BarChart3,
    items: [
      L("Previdenciários", "/relatorios/previdenciarios", "relatorios.previdenciarios"),
      L("Benefícios", "/relatorios/beneficios", "relatorios.beneficios"),
      L("Folha", "/relatorios/folha", "relatorios.folha"),
      L("Financeiros", "/relatorios/financeiros", "relatorios.financeiros"),
      L("Gerenciais", "/relatorios/gerenciais", "relatorios.gerenciais"),
      L("Estatísticos", "/relatorios/estatisticos", "relatorios.estatisticos"),
      L("eSocial", "/relatorios/esocial", "relatorios.esocial"),
      L("COMPREV", "/relatorios/comprev", "relatorios.comprev"),
    ],
  },
  // a tela de auditoria tem os filtros por categoria (alterações, cálculos, exclusões, acessos...)
  { key: "auditoria", label: "Auditoria", icon: ShieldCheck, href: "/auditoria", module: "auditoria" },
  { key: "portal", label: "Portal do Segurado", icon: UserRound, href: "/portal", module: "portal" },
  {
    key: "admin", label: "Administração", icon: Settings,
    items: [
      L("Usuários", "/administracao/usuarios", "admin.usuarios", { section: "Acesso" }),
      L("Perfis", "/administracao/perfis", "admin.perfis"),
      L("Permissões", "/administracao/permissoes", "admin.permissoes"),
      L("Instituição", "/administracao/instituicao", "admin.instituicao", { section: "Instituição" }),
      L("Exercícios", "/administracao/exercicios", "admin.exercicios"),
      L("Competências", "/administracao/competencias", "admin.competencias"),
      L("Parâmetros", "/administracao/parametros", "admin.parametros"),
    ],
  },
];

/** Todas as telas navegáveis (usado pela pesquisa global e pela página "Em desenvolvimento"). */
export function flatScreens(): (MenuLeaf & { group: string })[] {
  const out: (MenuLeaf & { group: string })[] = [];
  for (const g of MENU) {
    if (g.href && g.module) out.push({ label: g.label, href: g.href, module: g.module, group: g.label });
    for (const it of g.items || []) out.push({ ...it, group: g.label });
  }
  return out;
}

export function findScreenByPath(pathname: string) {
  return flatScreens().find((s) => s.href.split("?")[0] === pathname);
}
