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

export type MenuLeaf = { label: string; href: string; module: string };
export type MenuGroup = {
  key: string;
  label: string;
  icon: LucideIcon;
  href?: string;
  module?: string;
  items?: MenuLeaf[];
};

const L = (label: string, href: string, module: string): MenuLeaf => ({ label, href, module });

export const MENU: MenuGroup[] = [
  {
    key: "principal", label: "Principal", icon: LayoutDashboard,
    items: [
      L("Painel Geral", "/", "painel"),
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
    key: "cadastros", label: "Gestão de Cadastros", icon: Users,
    items: [
      // a admissão, os vínculos e o histórico funcional ficam em Servidores › Pasta do Servidor
      L("Servidores", "/cadastros/servidores", "cadastros.vinculos"),
      L("Dependentes", "/cadastros/dependentes", "cadastros.dependentes"),
      L("Importação de segurados", "/cadastros/importacao", "cadastros.importacao"),
      L("Órgãos", "/cadastros/orgaos", "cadastros.orgaos"),
      L("Cargos", "/cadastros/cargos", "cadastros.cargos"),
      L("Lotação", "/cadastros/lotacao", "cadastros.lotacao"),
      L("Entes", "/cadastros/entes", "cadastros.entes"),
      L("Bancos", "/cadastros/bancos", "cadastros.bancos"),
      L("Agências", "/cadastros/agencias", "cadastros.agencias"),
    ],
  },
  {
    key: "previdenciaria", label: "Gestão Previdenciária", icon: FileSearch,
    items: [
      L("Histórico Contributivo", "/previdenciaria/historico-contributivo", "previdenciaria.historico_contributivo"),
      L("Tempo de Contribuição", "/previdenciaria/tempo-contribuicao", "previdenciaria.tempo_contribuicao"),
      L("Regras de Aposentadoria", "/previdenciaria/regras", "previdenciaria.regras"),
      L("Simulação de Aposentadoria", "/previdenciaria/simulacao", "previdenciaria.simulacao"),
      L("CTC", "/previdenciaria/ctc", "previdenciaria.ctc"),
      L("Averbações", "/previdenciaria/averbacoes", "previdenciaria.averbacoes"),
    ],
  },
  {
    key: "concessao", label: "Concessão de Benefícios", icon: BadgeCheck,
    items: [
      L("Aposentadoria", "/concessao/aposentadoria", "concessao.aposentadoria"),
      L("Pensão", "/concessao/pensao", "concessao.pensao"),
      L("Revisão", "/concessao/revisao", "concessao.revisao"),
      L("Alteração de Benefício", "/concessao/alteracao", "concessao.alteracao"),
      L("Suspensão", "/concessao/suspensao", "concessao.suspensao"),
      L("Cessação", "/concessao/cessacao", "concessao.cessacao"),
      L("Reversão", "/concessao/reversao", "concessao.reversao"),
      L("Leitura inteligente (IA)", "/concessao/leitura", "concessao.leitura"),
      L("Processos", "/concessao/processos", "concessao.processos"),
      L("Modelos de portaria", "/concessao/modelos", "concessao.modelos"),
      L("Checklist de documentos", "/concessao/checklist", "concessao.modelos"),
    ],
  },
  {
    key: "folha", label: "Folha de Benefícios", icon: Wallet,
    items: [
      L("Painel da Folha", "/folha", "folha.painel"),
      L("Beneficiários", "/folha/beneficiarios", "folha.beneficiarios"),
      L("Isenção de IR (moléstia grave)", "/folha/isencoes-ir", "folha.beneficiarios"),
      L("Rubricas", "/folha/rubricas", "folha.rubricas"),
      L("Folha Mensal", "/folha/folha-mensal", "folha.folha_mensal"),
      L("Cálculo", "/folha/calculo", "folha.calculo"),
      L("Conferência", "/folha/conferencia", "folha.conferencia"),
      L("Retroativos", "/folha/retroativos", "folha.retroativos"),
      L("Diferenças", "/folha/diferencas", "folha.diferencas"),
      L("Consignações", "/folha/consignacoes", "folha.consignacoes"),
      L("Consignatárias", "/folha/consignatarias", "folha.consignacoes"),
      L("Pensão Alimentícia", "/folha/pensao-alimenticia", "folha.pensao_alimenticia"),
      L("13º Salário", "/folha/decimo-terceiro", "folha.decimo_terceiro"),
      L("Fechamento", "/folha/fechamento", "folha.fechamento"),
      L("Reabertura", "/folha/reabertura", "folha.reabertura"),
      L("Arquivo Bancário", "/folha/arquivo-bancario", "folha.arquivo_bancario"),
      L("Contracheques", "/folha/contracheques", "folha.contracheques"),
      L("Informe de Rendimentos", "/folha/informe-rendimentos", "folha.informe_rendimentos"),
      L("Relatórios", "/folha/relatorios", "folha.relatorios"),
    ],
  },
  {
    key: "ativos", label: "Folha de Ativos", icon: Briefcase,
    items: [
      L("Folhas", "/ativos/folhas", "ativos.folha"),
      L("Lançamentos", "/ativos/lancamentos", "ativos.lancamentos"),
      L("Tabela de Vencimentos", "/ativos/vencimentos", "ativos.vencimentos"),
      L("Rubricas", "/ativos/rubricas", "ativos.rubricas"),
      L("Ficha financeira (importação)", "/ativos/ficha-financeira", "ativos.ficha_financeira"),
    ],
  },
  {
    key: "esocial", label: "eSocial RPPS", icon: Send,
    items: [
      L("Painel", "/esocial", "esocial.painel"),
      L("S-2400", "/esocial/s-2400", "esocial.s2400"),
      L("S-2410", "/esocial/s-2410", "esocial.s2410"),
      L("S-1207", "/esocial/s-1207", "esocial.s1207"),
      L("Eventos", "/esocial/eventos", "esocial.eventos"),
      L("Transmissão", "/esocial/transmissao", "esocial.transmissao"),
      L("Retornos", "/esocial/retornos", "esocial.retornos"),
      L("Rejeições", "/esocial/rejeicoes", "esocial.rejeicoes"),
      L("Pendências", "/esocial/pendencias", "esocial.pendencias"),
      L("Histórico de envios", "/esocial/historico", "esocial.historico"),
    ],
  },
  {
    key: "arrecadacao", label: "Arrecadação", icon: Landmark,
    items: [
      L("Contribuição do Servidor", "/arrecadacao/servidor", "arrecadacao.servidor"),
      L("Contribuição Patronal", "/arrecadacao/patronal", "arrecadacao.patronal"),
      L("Aportes", "/arrecadacao/aportes", "arrecadacao.aportes"),
      L("Parcelamentos", "/arrecadacao/parcelamentos", "arrecadacao.parcelamentos"),
      L("Receitas", "/arrecadacao/receitas", "arrecadacao.receitas"),
      L("Conciliação", "/arrecadacao/conciliacao", "arrecadacao.conciliacao"),
      L("Divergências", "/arrecadacao/divergencias", "arrecadacao.divergencias"),
      L("Alíquotas", "/arrecadacao/aliquotas", "arrecadacao.aliquotas"),
    ],
  },
  {
    key: "comprev", label: "COMPREV", icon: ArrowLeftRight,
    items: [
      L("Processos", "/comprev/processos", "comprev.processos"),
      L("Recebimentos", "/comprev/recebimentos", "comprev.recebimentos"),
      L("Pagamentos", "/comprev/pagamentos", "comprev.pagamentos"),
      L("Fluxo Mensal", "/comprev/fluxo", "comprev.fluxo"),
      L("Indicadores", "/comprev/indicadores", "comprev.indicadores"),
      L("Relatórios", "/comprev/relatorios", "comprev.relatorios"),
    ],
  },
  {
    key: "recadastramento", label: "Recadastramento", icon: ClipboardCheck,
    items: [
      L("Campanhas", "/recadastramento/campanhas", "recadastramento.campanhas"),
      L("Segurados", "/recadastramento/segurados", "recadastramento.segurados"),
      L("Beneficiários", "/recadastramento/beneficiarios", "recadastramento.beneficiarios"),
      L("Pendências", "/recadastramento/pendencias", "recadastramento.pendencias"),
    ],
  },
  {
    key: "provadevida", label: "Prova de Vida", icon: Fingerprint,
    items: [
      L("Campanhas", "/prova-de-vida/campanhas", "provadevida.campanhas"),
      L("Realizadas", "/prova-de-vida/realizadas", "provadevida.realizadas"),
      L("Pendentes", "/prova-de-vida/pendentes", "provadevida.pendentes"),
      L("Bloqueados", "/prova-de-vida/bloqueados", "provadevida.bloqueados"),
      L("Relatórios", "/prova-de-vida/relatorios", "provadevida.relatorios"),
    ],
  },
  {
    key: "financeiro", label: "Gestão Financeira", icon: Banknote,
    items: [
      L("Pagamentos", "/financeiro/pagamentos", "financeiro.pagamentos"),
      L("Arquivos Bancários", "/financeiro/arquivos-bancarios", "financeiro.arquivos_bancarios"),
      L("Bancos", "/financeiro/bancos", "financeiro.bancos"),
      L("Conciliação", "/financeiro/conciliacao", "financeiro.conciliacao"),
      L("Integração Contábil", "/financeiro/integracao-contabil", "financeiro.integracao_contabil"),
    ],
  },
  {
    key: "atuarial", label: "Avaliação Atuarial", icon: Calculator,
    items: [
      L("Base de Dados (SPREV)", "/atuarial/base-dados", "atuarial.base"),
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
  {
    key: "auditoria", label: "Auditoria", icon: ShieldCheck,
    items: [
      L("Alterações", "/auditoria?categoria=alteracoes", "auditoria"),
      L("Cálculos", "/auditoria?categoria=calculos", "auditoria"),
      L("Exclusões", "/auditoria?categoria=exclusoes", "auditoria"),
      L("Usuários", "/auditoria?categoria=usuarios", "auditoria"),
      L("Acessos", "/auditoria?categoria=acessos", "auditoria"),
      L("Fechamentos", "/auditoria?categoria=fechamentos", "auditoria"),
      L("Reaberturas", "/auditoria?categoria=reaberturas", "auditoria"),
      L("Exportações", "/auditoria?categoria=exportacoes", "auditoria"),
    ],
  },
  { key: "portal", label: "Portal do Segurado", icon: UserRound, href: "/portal", module: "portal" },
  {
    key: "admin", label: "Administração", icon: Settings,
    items: [
      L("Usuários", "/administracao/usuarios", "admin.usuarios"),
      L("Perfis", "/administracao/perfis", "admin.perfis"),
      L("Permissões", "/administracao/permissoes", "admin.permissoes"),
      L("Instituição", "/administracao/instituicao", "admin.instituicao"),
      L("Parâmetros", "/administracao/parametros", "admin.parametros"),
      L("Exercícios", "/administracao/exercicios", "admin.exercicios"),
      L("Competências", "/administracao/competencias", "admin.competencias"),
      L("Tabelas", "/administracao/tabelas", "admin.tabelas"),
      L("Configurações", "/administracao/configuracoes", "admin.configuracoes"),
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
