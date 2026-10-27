"""
Catálogo de módulos e ações do SIST.

É a fonte única para o RBAC: o comando `sync_permissions` (executado também
após cada `migrate`) cria/atualiza a tabela de módulos e permissões a partir
deste arquivo, e define as permissões iniciais dos perfis de sistema.

phase: fase do roadmap em que o módulo será entregue (None = a definir).
implemented: True quando o módulo já possui funcionalidade real.
"""
from dataclasses import dataclass

V, I, E, X = "visualizar", "incluir", "editar", "excluir"
CALC, FECH, REAB, EXP, APR = "calcular", "fechar", "reabrir", "exportar", "aprovar"

ACTIONS = [
    (V, "Visualizar"), (I, "Incluir"), (E, "Editar"), (X, "Excluir"),
    (CALC, "Calcular"), (FECH, "Fechar"), (REAB, "Reabrir"),
    (EXP, "Exportar"), (APR, "Aprovar"),
]
ACTION_CODES = [a for a, _ in ACTIONS]

CRUD = [V, I, E, X]
CRUD_EXP = [V, I, E, X, EXP]


@dataclass(frozen=True)
class ModuleDef:
    code: str
    name: str
    group: str
    actions: tuple
    phase: int | None = None
    implemented: bool = False

    @property
    def rpps_only(self) -> bool:
        return self.group in RPPS_GROUPS or self.code in RPPS_MODULES


# Módulos exclusivos de RPPS: ficam ocultos (sem permissão efetiva) em Prefeituras,
# Autarquias e Fundos. Cadastro, Protocolo, Auditoria e Administração servem a todos.
RPPS_GROUPS = {"previdenciaria", "concessao", "folha", "comprev", "provadevida", "atuarial"}
RPPS_MODULES = {"cadastros.instituidores", "recadastramento.beneficiarios", "esocial.s2400", "esocial.s2410",
                "relatorios.previdenciarios", "relatorios.beneficios", "relatorios.comprev", "portal"}


def module_available(code: str, institution_kind: str | None) -> bool:
    mdef = MODULES_BY_CODE.get(code)
    if mdef is None or institution_kind in (None, "RPPS"):
        return True
    return not mdef.rpps_only


GROUPS = [
    ("geral", "Geral"),
    ("protocolo", "Protocolo"),
    ("cadastros", "Gestão de Cadastros"),
    ("previdenciaria", "Gestão Previdenciária"),
    ("concessao", "Concessão de Benefícios"),
    ("folha", "Folha de Benefícios"),
    ("ativos", "Folha de Ativos"),
    ("esocial", "eSocial RPPS"),
    ("arrecadacao", "Arrecadação"),
    ("comprev", "COMPREV"),
    ("recadastramento", "Recadastramento"),
    ("provadevida", "Prova de Vida"),
    ("financeiro", "Gestão Financeira"),
    ("atuarial", "Avaliação Atuarial"),
    ("relatorios", "Relatórios"),
    ("auditoria", "Auditoria"),
    ("portal", "Portal do Segurado"),
    ("admin", "Administração"),
]


def _m(code, name, group, actions, phase=None, implemented=False):
    return ModuleDef(code, name, group, tuple(actions), phase, implemented)


MODULES: list[ModuleDef] = [
    # Geral
    _m("painel", "Painel Geral", "geral", [V], 1, True),
    _m("alertas", "Central de Alertas", "geral", [V, E], 1, True),
    _m("calendario", "Calendário", "geral", CRUD, 2),
    # Protocolo (todos os tipos de órgão)
    _m("protocolo.processos", "Processos (Protocolo)", "protocolo", [V, I, E, FECH, REAB, EXP], 2, True),
    _m("protocolo.configuracao", "Configuração do Protocolo", "protocolo", CRUD, 2, True),
    # Cadastros
    _m("cadastros.segurados", "Cadastro Único (pessoas)", "cadastros", CRUD_EXP, 2, True),
    _m("cadastros.dependentes", "Dependentes", "cadastros", CRUD_EXP, 2, True),
    _m("cadastros.importacao", "Importação de segurados", "cadastros", [V, I], 2, True),
    _m("cadastros.instituidores", "Instituidores", "cadastros", CRUD_EXP, 4),
    _m("cadastros.entes", "Entes", "cadastros", CRUD, 2, True),
    _m("cadastros.orgaos", "Órgãos", "cadastros", CRUD, 2, True),
    _m("cadastros.cargos", "Cargos", "cadastros", CRUD, 2, True),
    _m("cadastros.vinculos", "Vínculos", "cadastros", CRUD_EXP, 2, True),
    _m("cadastros.bancos", "Bancos", "cadastros", CRUD, 2, True),
    _m("cadastros.agencias", "Agências", "cadastros", CRUD, 2, True),
    _m("cadastros.lotacao", "Lotação", "cadastros", CRUD, 2, True),
    _m("cadastros.tabelas", "Tabelas auxiliares", "cadastros", CRUD, 2),
    # Previdenciária
    _m("previdenciaria.historico_funcional", "Histórico Funcional", "previdenciaria", CRUD_EXP, 2),
    _m("previdenciaria.historico_contributivo", "Histórico Contributivo", "previdenciaria", CRUD_EXP, 3, True),
    _m("previdenciaria.tempo_contribuicao", "Tempo de Contribuição", "previdenciaria", [V, CALC, EXP], 3, True),
    _m("previdenciaria.regras", "Regras de Aposentadoria", "previdenciaria", CRUD + [APR], 3, True),
    _m("previdenciaria.simulacao", "Simulação de Aposentadoria", "previdenciaria", [V, CALC, EXP], 3, True),
    _m("previdenciaria.elegibilidade", "Elegibilidade", "previdenciaria", [V, CALC, EXP], 3),
    _m("previdenciaria.ctc", "CTC", "previdenciaria", CRUD_EXP + [APR], 3, True),
    _m("previdenciaria.averbacoes", "Averbações", "previdenciaria", CRUD + [APR], 3, True),
    _m("previdenciaria.certidoes", "Certidões", "previdenciaria", CRUD_EXP + [APR], 3),
    _m("previdenciaria.processos", "Processos Previdenciários", "previdenciaria", CRUD_EXP + [APR], 3),
    # Concessão
    _m("concessao.aposentadoria", "Aposentadoria", "concessao", CRUD_EXP + [CALC, APR], 4, True),
    _m("concessao.pensao", "Pensão", "concessao", CRUD_EXP + [CALC, APR], 4, True),
    _m("concessao.revisao", "Revisão", "concessao", CRUD_EXP + [CALC], 4, True),
    _m("concessao.alteracao", "Alteração de Benefício", "concessao", CRUD + [APR], 4),
    _m("concessao.suspensao", "Suspensão", "concessao", CRUD + [APR], 4, True),
    _m("concessao.cessacao", "Cessação", "concessao", CRUD + [APR], 4, True),
    _m("concessao.reversao", "Reversão", "concessao", CRUD + [APR], 4, True),
    _m("concessao.processos", "Processos de Concessão", "concessao", CRUD_EXP + [APR], 4, True),
    # Decisões da concessão (segregação de funções — mapeamento PREVIBAM)
    _m("concessao.juridico", "Parecer Jurídico", "concessao", [V, APR], 4, True),
    _m("concessao.controle_interno", "Controle Interno (conformidade)", "concessao", [V, APR], 4, True),
    _m("concessao.presidencia", "Presidência (assinatura de portarias)", "concessao", [V, APR], 4, True),
    _m("concessao.implantacao", "Publicação e implantação em folha", "concessao", [V, APR], 4, True),
    _m("concessao.tce", "Envio ao TCE-RJ e julgamento", "concessao", [V, E], 4, True),
    _m("concessao.modelos", "Modelos de portaria e ofício", "concessao", CRUD, 4, True),
    _m("concessao.leitura", "Leitura inteligente de processos", "concessao", [V, I, E], 9, True),
    # Folha
    _m("folha.painel", "Painel da Folha", "folha", [V], 5, True),
    _m("folha.beneficiarios", "Beneficiários", "folha", CRUD_EXP, 4, True),
    _m("folha.rubricas", "Rubricas", "folha", CRUD + [APR], 5, True),
    _m("folha.folha_mensal", "Folha Mensal", "folha", [V, I, E, X, EXP], 5, True),
    _m("folha.calculo", "Cálculo", "folha", [V, CALC], 5, True),
    _m("folha.conferencia", "Conferência", "folha", [V, APR, EXP], 5, True),
    _m("folha.retroativos", "Retroativos", "folha", CRUD + [CALC, APR], 5, True),
    _m("folha.diferencas", "Diferenças", "folha", CRUD + [CALC], 5, True),
    _m("folha.consignacoes", "Consignações", "folha", CRUD_EXP, 5, True),
    _m("folha.pensao_alimenticia", "Pensão Alimentícia", "folha", CRUD, 5, True),
    _m("folha.decimo_terceiro", "13º Salário", "folha", [V, CALC, EXP], 5, True),
    _m("folha.fechamento", "Fechamento", "folha", [V, FECH], 5, True),
    _m("folha.reabertura", "Reabertura", "folha", [V, REAB], 5, True),
    _m("folha.arquivo_bancario", "Arquivo Bancário", "folha", [V, EXP], 5, True),
    _m("folha.contracheques", "Contracheques", "folha", [V, EXP], 5, True),
    _m("folha.informe_rendimentos", "Informe de Rendimentos", "folha", [V, CALC, EXP], 5, True),
    _m("folha.relatorios", "Relatórios da Folha", "folha", [V, EXP], 5, True),
    # Folha de Ativos (servidores em atividade) — para todos os tipos de órgão
    _m("ativos.vencimentos", "Tabela de Vencimentos", "ativos", CRUD, 9, True),
    _m("ativos.rubricas", "Rubricas (ativos)", "ativos", CRUD, 9, True),
    _m("ativos.lancamentos", "Lançamentos (ativos)", "ativos", CRUD, 9, True),
    _m("ativos.folha", "Folha de Ativos", "ativos", [V, I, X, CALC, APR, FECH, REAB, EXP], 9, True),
    _m("ativos.ficha_financeira", "Ficha financeira e contribuições", "ativos", [V, I, EXP], 9, True),
    # eSocial
    _m("esocial.painel", "Painel eSocial", "esocial", [V], 6, True),
    _m("esocial.s2400", "S-2400", "esocial", [V, I, E, APR], 6, True),
    _m("esocial.s2410", "S-2410", "esocial", [V, I, E, APR], 6, True),
    _m("esocial.s1207", "S-1207", "esocial", [V, I, E, APR], 6, True),
    _m("esocial.eventos", "Eventos", "esocial", [V, EXP], 6, True),
    _m("esocial.retornos", "Retornos", "esocial", [V, I, EXP], 6, True),
    _m("esocial.rejeicoes", "Rejeições", "esocial", [V, E], 6, True),
    _m("esocial.pendencias", "Pendências", "esocial", [V, E], 6, True),
    _m("esocial.historico", "Histórico de envios", "esocial", [V, EXP], 6, True),
    _m("esocial.transmissao", "Transmissão", "esocial", [V, I, E], 9, True),
    # Arrecadação
    _m("arrecadacao.servidor", "Contribuição do Servidor", "arrecadacao", CRUD_EXP, 7, True),
    _m("arrecadacao.patronal", "Contribuição Patronal", "arrecadacao", CRUD_EXP, 7, True),
    _m("arrecadacao.aportes", "Aportes", "arrecadacao", CRUD_EXP, 7, True),
    _m("arrecadacao.parcelamentos", "Parcelamentos", "arrecadacao", CRUD_EXP, 7, True),
    _m("arrecadacao.receitas", "Receitas", "arrecadacao", CRUD_EXP, 7, True),
    _m("arrecadacao.conciliacao", "Conciliação", "arrecadacao", [V, E, APR, EXP], 7, True),
    _m("arrecadacao.divergencias", "Divergências", "arrecadacao", [V, E, EXP], 7, True),
    _m("arrecadacao.aliquotas", "Alíquotas de contribuição", "arrecadacao", [V, I], 7, True),
    # COMPREV
    _m("comprev.processos", "Processos COMPREV", "comprev", CRUD_EXP, 9, True),
    _m("comprev.recebimentos", "Recebimentos", "comprev", CRUD_EXP, 9, True),
    _m("comprev.pagamentos", "Pagamentos", "comprev", CRUD_EXP, 9, True),
    _m("comprev.fluxo", "Fluxo Mensal", "comprev", [V, EXP], 9, True),
    _m("comprev.indicadores", "Indicadores", "comprev", [V], 9, True),
    _m("comprev.relatorios", "Relatórios COMPREV", "comprev", [V, EXP], 9, True),
    # Recadastramento
    _m("recadastramento.campanhas", "Campanhas de Recadastramento", "recadastramento", CRUD + [FECH], 9, True),
    _m("recadastramento.segurados", "Recadastramento de Segurados", "recadastramento", [V, E, APR], 9, True),
    _m("recadastramento.beneficiarios", "Recadastramento de Beneficiários", "recadastramento", [V, E, APR], 9, True),
    _m("recadastramento.pendencias", "Pendências de Recadastramento", "recadastramento", [V, E, EXP], 9, True),
    # Prova de vida
    _m("provadevida.campanhas", "Campanhas de Prova de Vida", "provadevida", CRUD + [FECH], 9, True),
    _m("provadevida.realizadas", "Provas Realizadas", "provadevida", [V, I, E, APR], 9, True),
    _m("provadevida.pendentes", "Provas Pendentes", "provadevida", [V, E, EXP], 9, True),
    _m("provadevida.bloqueados", "Bloqueados", "provadevida", [V, E, APR], 9, True),
    _m("provadevida.relatorios", "Relatórios de Prova de Vida", "provadevida", [V, EXP], 9, True),
    # Financeiro
    _m("financeiro.pagamentos", "Pagamentos", "financeiro", CRUD_EXP + [APR], 7, True),
    _m("financeiro.arquivos_bancarios", "Arquivos Bancários", "financeiro", [V, I, EXP], 7, True),
    _m("financeiro.bancos", "Bancos (Financeiro)", "financeiro", CRUD, 7, True),
    _m("financeiro.conciliacao", "Conciliação Bancária", "financeiro", [V, E, APR, EXP], 7, True),
    _m("financeiro.integracao_contabil", "Integração Contábil", "financeiro", CRUD_EXP + [APR], 7, True),
    # Avaliação Atuarial (estrutura e leiaute SPREV na Fase 1; dados a partir das Fases 2, 4 e 5)
    _m("atuarial.base", "Base de Dados Atuarial", "atuarial", [V, I, EXP], 1, True),
    # Relatórios
    _m("relatorios.previdenciarios", "Relatórios Previdenciários", "relatorios", [V, EXP], 9, True),
    _m("relatorios.beneficios", "Relatórios de Benefícios", "relatorios", [V, EXP], 9, True),
    _m("relatorios.folha", "Relatórios de Folha", "relatorios", [V, EXP], 9, True),
    _m("relatorios.financeiros", "Relatórios Financeiros", "relatorios", [V, EXP], 9, True),
    _m("relatorios.gerenciais", "Relatórios Gerenciais", "relatorios", [V, EXP], 9, True),
    _m("relatorios.estatisticos", "Relatórios Estatísticos", "relatorios", [V, EXP], 9, True),
    _m("relatorios.esocial", "Relatórios eSocial", "relatorios", [V, EXP], 9, True),
    _m("relatorios.comprev", "Relatórios COMPREV", "relatorios", [V, EXP], 9, True),
    # Auditoria (implementada na Fase 1)
    _m("auditoria", "Auditoria", "auditoria", [V, EXP], 1, True),
    # Portal
    _m("portal", "Portal do Segurado (gestão de acessos e solicitações)", "portal", [V, E], 8, True),
    # Administração
    _m("admin.usuarios", "Usuários", "admin", [V, I, E], 1, True),
    _m("admin.perfis", "Perfis", "admin", CRUD, 1, True),
    _m("admin.permissoes", "Permissões", "admin", [V, E], 1, True),
    _m("admin.instituicao", "Instituição", "admin", [V, I, E], 1, True),
    _m("admin.parametros", "Parâmetros", "admin", [V, I], 1, True),
    _m("admin.exercicios", "Exercícios", "admin", [V, I, FECH, REAB], 1, True),
    _m("admin.competencias", "Competências", "admin", [V, I, E, FECH, REAB], 1, True),
    _m("admin.tabelas", "Tabelas", "admin", CRUD, 2),
    _m("admin.configuracoes", "Configurações", "admin", [V, E]),
]

MODULES_BY_CODE = {m.code: m for m in MODULES}


# ---------------------------------------------------------------------------
# Perfis de sistema e suas permissões iniciais
# ---------------------------------------------------------------------------
def _all():
    return {(m.code, a) for m in MODULES for a in m.actions}


def _filter(groups=None, codes=None, actions=None):
    result = set()
    for m in MODULES:
        if (groups and m.group in groups) or (codes and m.code in codes):
            for a in m.actions:
                if actions is None or a in actions:
                    result.add((m.code, a))
    return result


def _view_all(exclude_groups=()):
    return {(m.code, V) for m in MODULES if m.group not in exclude_groups and V in m.actions}


# Atos decisórios: cada um é de um setor (não entram no perfil Previdenciário)
DECISION_MODULES = {"concessao.juridico", "concessao.controle_interno", "concessao.presidencia", "concessao.implantacao"}
CONCESSION_VIEW = _filter(groups={"concessao", "cadastros", "previdenciaria"}, actions={V})

PROTOCOLO_BASE = {("protocolo.processos", V), ("protocolo.processos", I), ("protocolo.processos", E)}
BASE = {("painel", V), ("alertas", V)} | PROTOCOLO_BASE  # todos os setores abrem e tramitam processos
# Incluídas também nos perfis de sistema já existentes a cada sync_permissions (sem reset)
ALWAYS_SYNC = PROTOCOLO_BASE

SYSTEM_ROLES = {
    "MASTER": {
        "name": "Master",
        "description": "Acesso irrestrito. Único perfil que pode conceder o perfil MASTER.",
        "permissions": _all,
    },
    "ADMINISTRADOR": {
        "name": "Administrador",
        "description": "Administração geral do sistema e de todos os módulos.",
        "permissions": _all,
    },
    "PREVIDENCIARIO": {
        "name": "Previdenciário",
        "description": "Cadastros, gestão previdenciária e concessão de benefícios.",
        "permissions": lambda: BASE | {("alertas", E)}
        | {p for p in _filter(groups={"cadastros", "previdenciaria", "concessao", "recadastramento", "provadevida",
                                     "geral", "atuarial", "protocolo"}) if p[0] not in DECISION_MODULES}
        | _filter(groups={"folha"}, actions={V})
        | _filter(codes={"relatorios.previdenciarios", "relatorios.beneficios", "relatorios.estatisticos", "portal"}, actions={V, EXP}),
    },
    "FOLHA": {
        "name": "Folha",
        "description": "Motor de cálculo, folha de benefícios e eSocial.",
        "permissions": lambda: BASE | {("alertas", E)}
        | _filter(groups={"folha", "ativos", "esocial"})
        | _filter(codes={"concessao.implantacao"})
        | _filter(groups={"cadastros", "previdenciaria", "concessao"}, actions={V})
        | _filter(codes={"relatorios.folha", "relatorios.beneficios", "relatorios.esocial"}, actions={V, EXP}),
    },
    "FINANCEIRO": {
        "name": "Financeiro",
        "description": "Arrecadação, COMPREV, pagamentos e arquivos bancários.",
        "permissions": lambda: BASE | {("alertas", E)}
        | _filter(groups={"arrecadacao", "comprev", "financeiro"})
        | _filter(groups={"folha"}, actions={V, EXP})
        | _filter(groups={"cadastros"}, actions={V})
        | _filter(codes={"relatorios.financeiros", "relatorios.comprev", "relatorios.gerenciais"}, actions={V, EXP}),
    },
    "CONTABILIDADE": {
        "name": "Contabilidade",
        "description": "Integração contábil (DE/PARA) e consulta financeira.",
        "permissions": lambda: BASE
        | _filter(groups={"folha", "arrecadacao", "financeiro", "comprev", "atuarial"}, actions={V, EXP})
        | _filter(codes={"financeiro.integracao_contabil"})
        | _filter(codes={"relatorios.financeiros", "relatorios.gerenciais"}, actions={V, EXP}),
    },
    "JURIDICO": {
        "name": "Procuradoria Jurídica",
        "description": "Parecer jurídico nos processos de concessão e revisão; consulta aos autos.",
        "permissions": lambda: BASE | CONCESSION_VIEW | _filter(codes={"concessao.juridico", "concessao.modelos"}),
    },
    "CONTROLE_INTERNO": {
        "name": "Controle Interno",
        "description": "Análise de conformidade das concessões; consulta e auditoria.",
        "permissions": lambda: BASE | CONCESSION_VIEW | _filter(codes={"concessao.controle_interno", "auditoria"}),
    },
    "PRESIDENCIA": {
        "name": "Presidência",
        "description": "Assina portarias de concessão, revisão e anulação; indefere requerimentos.",
        "permissions": lambda: BASE | CONCESSION_VIEW | _filter(codes={"concessao.presidencia", "concessao.tce"})
        | _filter(groups={"folha"}, actions={V}),
    },
    "AUDITOR": {
        "name": "Auditor",
        "description": "Consulta e exportação de todos os módulos, inclusive auditoria.",
        "permissions": lambda: _filter(groups={g for g, _ in GROUPS}, actions={V, EXP}),
    },
    "CONSULTA": {
        "name": "Consulta",
        "description": "Somente visualização (exceto administração e auditoria).",
        "permissions": lambda: _view_all(exclude_groups=("admin", "auditoria")),
    },
}
