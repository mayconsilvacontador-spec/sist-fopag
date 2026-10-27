"""
Verificações automáticas que alimentam a Central de Alertas.

Cada verificação recebe a instituição e devolve uma lista de AlertSpec com
base em dados REAIS do banco. Novos módulos (cadastro, folha, eSocial...)
registram suas próprias verificações com @check, por exemplo:
  - CPF duplicado, conta bancária ausente, benefício sem plano,
    folha não fechada, eSocial rejeitado, prova de vida vencida.
"""
from dataclasses import dataclass

from django.db.models import Count
from django.utils import timezone

from .models import Severity


@dataclass
class AlertSpec:
    severity: str
    title: str
    message: str = ""
    module: str = ""
    link: str = ""
    object_type: str = ""
    object_id: str = ""
    key: str = ""  # diferencia ocorrências da mesma verificação


CHECKS: dict = {}


def check(code: str):
    def decorator(fn):
        CHECKS[code] = fn
        return fn
    return decorator


@check("EXERCICIO_CORRENTE_AUSENTE")
def exercicio_corrente(institution):
    from apps.institutions.models import FiscalYear

    year = timezone.localdate().year
    if FiscalYear.objects.filter(institution=institution, year=year).exists():
        return []
    return [AlertSpec(
        Severity.ATENCAO, f"Exercício {year} não cadastrado",
        f"Cadastre o exercício {year} em Administração › Exercícios.",
        module="admin.exercicios", link="/administracao/exercicios",
    )]


@check("COMPETENCIA_REFERENCIA_AUSENTE")
def competencia_referencia(institution):
    from apps.institutions.models import Competence

    if Competence.objects.filter(institution=institution, is_reference=True).exists():
        return []
    return [AlertSpec(
        Severity.ATENCAO, "Competência de referência não definida",
        "Defina a competência de referência em Administração › Competências.",
        module="admin.competencias", link="/administracao/competencias",
    )]


@check("COMPETENCIAS_ANTERIORES_ABERTAS")
def competencias_anteriores_abertas(institution):
    from apps.institutions.models import Competence, CompetenceStatus

    ref = Competence.objects.filter(institution=institution, is_reference=True).first()
    if not ref:
        return []
    abertas = Competence.objects.filter(
        institution=institution, status=CompetenceStatus.ABERTA
    ).filter(year__lt=ref.year) | Competence.objects.filter(
        institution=institution, status=CompetenceStatus.ABERTA, year=ref.year, month__lt=ref.month
    )
    specs = []
    for comp in abertas.order_by("year", "month"):
        specs.append(AlertSpec(
            Severity.INFORMATIVO, f"Competência {comp} ainda aberta",
            f"A competência {comp} é anterior à referência ({ref}) e não foi fechada.",
            module="admin.competencias", link="/administracao/competencias",
            object_type="institutions.competence", object_id=str(comp.pk), key=str(comp.pk),
        ))
    return specs


@check("PLANO_SEGREGACAO_AUSENTE")
def planos_segregacao(institution):
    from apps.institutions.models import BenefitPlan, PlanKind

    specs = []
    for kind in PlanKind:
        if not BenefitPlan.objects.filter(institution=institution, kind=kind, active=True).exists():
            specs.append(AlertSpec(
                Severity.CRITICO, f"{kind.label} não cadastrado",
                "A segregação de massas exige o cadastro do plano. Sem ele, benefícios e "
                "receitas não poderão ser identificados por plano.",
                module="admin.instituicao", link="/administracao/instituicao", key=kind.value,
            ))
    return specs


@check("COMPRA_VIDAS_SEM_LOTE")
def compra_vidas_sem_lote(institution):
    from apps.institutions.models import LifePurchase

    if not institution.life_purchase_enabled:
        return []
    if LifePurchase.objects.filter(institution=institution, active=True).exists():
        return []
    return [AlertSpec(
        Severity.ATENCAO, "Compra de Vidas ativada sem lote registrado",
        "Registre o lote (data de corte, ato legal e valor transferido) em Administração › Instituição. "
        "Sem ele, as vidas transferidas não poderão ser vinculadas à folha da Compra de Vidas.",
        module="admin.instituicao", link="/administracao/instituicao",
    )]


@check("CODIGO_IBGE_AUSENTE")
def codigo_ibge_ausente(institution):
    if institution.ibge_code:
        return []
    return [AlertSpec(
        Severity.INFORMATIVO, "Código IBGE do ente não informado",
        "O código IBGE (CO_IBGE) é obrigatório na base de dados da avaliação atuarial. "
        "Informe-o em Administração › Instituição.",
        module="admin.instituicao", link="/administracao/instituicao",
    )]


@check("PESSOAS_SEM_NOME")
def pessoas_sem_nome(institution):
    from apps.people.models import Person

    n = Person.objects.filter(institution=institution, name="").count()
    if not n:
        return []
    return [AlertSpec(
        Severity.ATENCAO, f"{n} pessoa(s) importada(s) sem nome",
        "A base SPREV não traz o nome das pessoas. Complete pela consulta à Receita Federal "
        "(Cadastro Único › Completar nomes) ou edite cada cadastro.",
        module="cadastros.segurados", link="/cadastros/segurados?sem_nome=1",
    )]


@check("USUARIO_SEM_PERFIL")
def usuarios_sem_perfil(institution):
    from apps.accounts.models import Membership

    qs = (
        Membership.objects.filter(institution=institution, active=True, user__is_active=True)
        .annotate(n=Count("membership_roles")).filter(n=0).select_related("user")
    )
    return [
        AlertSpec(
            Severity.INFORMATIVO, f"Usuário {m.user.username} sem perfil de acesso",
            "O usuário está ativo, mas não possui nenhum perfil na instituição.",
            module="admin.usuarios", link="/administracao/usuarios",
            object_type="accounts.user", object_id=str(m.user_id), key=str(m.user_id),
        )
        for m in qs
    ]


@check("USUARIO_BLOQUEADO")
def usuarios_bloqueados(institution):
    from apps.accounts.models import User

    qs = User.objects.filter(
        memberships__institution=institution, locked_until__gt=timezone.now()
    ).distinct()
    return [
        AlertSpec(
            Severity.ATENCAO, f"Usuário {u.username} bloqueado por tentativas de login",
            f"Bloqueado até {timezone.localtime(u.locked_until):%d/%m/%Y %H:%M}.",
            module="admin.usuarios", link="/administracao/usuarios",
            object_type="accounts.user", object_id=str(u.pk), key=str(u.pk),
        )
        for u in qs
    ]
