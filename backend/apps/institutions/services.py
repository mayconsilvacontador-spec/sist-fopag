"""Regras de negócio de instituições, exercícios, competências e parâmetros."""
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from .models import (
    SEGMENT_PLAN_KIND, BenefitPlan, Competence, CompetenceStatus, FiscalYear, FiscalYearStatus,
    Institution, LifePurchase, Parameter, PayrollGroup, PlanKind, Segment,
)

GROUP_DEFAULTS = {
    Segment.FINANCEIRO: ("FIN", "Folha do Plano Financeiro"),
    Segment.PREVIDENCIARIO: ("PREV", "Folha do Plano Previdenciário"),
    Segment.COMPRA_VIDAS: ("PREV-CV", "Folha da Compra de Vidas"),
}

# Valores aceitos pelo filtro global de plano/folha
PLAN_FILTERS = {
    "TODOS": [Segment.FINANCEIRO, Segment.PREVIDENCIARIO, Segment.COMPRA_VIDAS],
    "FINANCEIRO": [Segment.FINANCEIRO],
    # Previdenciário consolidado = massa própria + compra de vidas (mesmo fundo)
    "PREVIDENCIARIO": [Segment.PREVIDENCIARIO, Segment.COMPRA_VIDAS],
    "PREVIDENCIARIO_PROPRIO": [Segment.PREVIDENCIARIO],
    "COMPRA_VIDAS": [Segment.COMPRA_VIDAS],
}


def get_reference_competence(institution: Institution) -> Competence | None:
    return Competence.objects.filter(institution=institution, is_reference=True).first()


def _plan_for(institution: Institution, segment: str) -> BenefitPlan | None:
    return (
        BenefitPlan.objects.filter(institution=institution, kind=SEGMENT_PLAN_KIND[segment], active=True)
        .order_by("code").first()
    )


@transaction.atomic
def ensure_payroll_groups(institution: Institution) -> list[PayrollGroup]:
    """
    Garante uma folha por massa. A folha da Compra de Vidas só existe (ativa)
    quando a instituição possui compra de vidas. Folhas não são excluídas.
    """
    wanted = [Segment.FINANCEIRO, Segment.PREVIDENCIARIO]
    if institution.life_purchase_enabled:
        wanted.append(Segment.COMPRA_VIDAS)
    for segment in wanted:
        if PayrollGroup.objects.filter(institution=institution, segment=segment).exists():
            continue
        plan = _plan_for(institution, segment)
        if plan is None:
            continue  # o alerta PLANO_SEGREGACAO_AUSENTE já aponta a falta do plano
        code, name = GROUP_DEFAULTS[segment]
        PayrollGroup.objects.create(institution=institution, segment=segment, code=code, name=name, plan=plan)
    return list(PayrollGroup.objects.filter(institution=institution))


def active_segments(institution: Institution) -> list[str]:
    segments = [Segment.FINANCEIRO, Segment.PREVIDENCIARIO]
    if institution.life_purchase_enabled:
        segments.append(Segment.COMPRA_VIDAS)
    return segments


def segments_for_filter(institution: Institution, plano: str | None) -> list[str]:
    """Massas incluídas no filtro, respeitando as que existem na instituição."""
    wanted = PLAN_FILTERS.get((plano or "TODOS").upper(), PLAN_FILTERS["TODOS"])
    available = active_segments(institution)
    return [s for s in wanted if s in available]


@transaction.atomic
def set_life_purchase(institution: Institution, enabled: bool, justification: str) -> Institution:
    """Liga/desliga a Compra de Vidas da instituição (sempre com justificativa)."""
    _require_justification(justification)
    institution = Institution.objects.select_for_update().get(pk=institution.pk)
    if institution.life_purchase_enabled == enabled:
        raise BusinessRuleError(
            "A Compra de Vidas já está " + ("ativada." if enabled else "desativada.")
        )
    if enabled:
        if institution.kind != "RPPS":
            raise BusinessRuleError("A Compra de Vidas só se aplica a instituições do tipo RPPS.")
        if _plan_for(institution, Segment.FINANCEIRO) is None or _plan_for(institution, Segment.PREVIDENCIARIO) is None:
            raise BusinessRuleError(
                "A Compra de Vidas exige os planos Financeiro e Previdenciário ativos (segregação de massas)."
            )
    elif LifePurchase.objects.filter(institution=institution, active=True).exists():
        raise BusinessRuleError(
            "Existem lotes de Compra de Vidas ativos. Inative-os antes de desativar a Compra de Vidas."
        )
    old = institution.life_purchase_enabled
    # update() evita o registro automático de auditoria: o evento abaixo leva a justificativa
    Institution.objects.filter(pk=institution.pk).update(life_purchase_enabled=enabled, updated_at=timezone.now())
    institution.life_purchase_enabled = enabled
    ensure_payroll_groups(institution)
    PayrollGroup.objects.filter(institution=institution, segment=Segment.COMPRA_VIDAS).update(active=enabled)
    log_event(
        "UPDATE", module="admin.instituicao", obj=institution,
        old={"possui_compra_de_vidas": old}, new={"possui_compra_de_vidas": enabled},
        justification=justification,
    )
    return institution


def validate_life_purchase(institution: Institution, data: dict, instance: LifePurchase | None = None) -> None:
    if not institution.life_purchase_enabled:
        raise BusinessRuleError("Ative a Compra de Vidas da instituição antes de registrar lotes.")
    origin, dest = data.get("origin_plan"), data.get("destination_plan")
    if origin and (origin.institution_id != institution.pk or origin.kind != PlanKind.FINANCEIRO):
        raise BusinessRuleError("O plano de origem deve ser o Plano Financeiro da instituição.")
    if dest and (dest.institution_id != institution.pk or dest.kind != PlanKind.PREVIDENCIARIO):
        raise BusinessRuleError("O plano de destino deve ser o Plano Previdenciário da instituição.")
    cutoff, effective = data.get("cutoff_date"), data.get("effective_date")
    if cutoff and effective and effective < cutoff:
        raise BusinessRuleError("O início do pagamento não pode ser anterior à data de corte.")


def next_life_purchase_number(institution: Institution) -> int:
    last = LifePurchase.objects.filter(institution=institution).order_by("-number").first()
    return (last.number + 1) if last else 1


@transaction.atomic
def set_reference_competence(competence: Competence) -> Competence:
    previous = Competence.objects.select_for_update().filter(
        institution_id=competence.institution_id, is_reference=True
    ).exclude(pk=competence.pk)
    for comp in previous:
        comp.is_reference = False
        comp.save(update_fields=["is_reference", "updated_at", "updated_by"])
    competence.is_reference = True
    competence.save(update_fields=["is_reference", "updated_at", "updated_by"])
    return competence


@transaction.atomic
def close_fiscal_year(fy: FiscalYear, user) -> FiscalYear:
    if fy.status == FiscalYearStatus.FECHADO:
        raise BusinessRuleError("O exercício já está fechado.")
    open_comps = fy.competences.filter(status=CompetenceStatus.ABERTA).count()
    if open_comps:
        raise BusinessRuleError(
            f"Existem {open_comps} competência(s) aberta(s) neste exercício. Feche-as antes."
        )
    fy.status = FiscalYearStatus.FECHADO
    fy.closed_at = timezone.now()
    fy.closed_by = user
    fy.save()
    log_event("CLOSE", module="admin.exercicios", obj=fy)
    return fy


@transaction.atomic
def reopen_fiscal_year(fy: FiscalYear, justification: str) -> FiscalYear:
    if fy.status != FiscalYearStatus.FECHADO:
        raise BusinessRuleError("O exercício não está fechado.")
    _require_justification(justification)
    fy.status = FiscalYearStatus.ABERTO
    fy.closed_at = None
    fy.closed_by = None
    fy.save()
    log_event("REOPEN", module="admin.exercicios", obj=fy, justification=justification)
    return fy


@transaction.atomic
def create_competence(institution: Institution, year: int, month: int) -> Competence:
    fy = FiscalYear.objects.filter(institution=institution, year=year).first()
    if fy is None:
        raise BusinessRuleError(f"Cadastre primeiro o exercício {year}.")
    if fy.status == FiscalYearStatus.FECHADO:
        raise BusinessRuleError(f"O exercício {year} está fechado.")
    if Competence.objects.filter(institution=institution, year=year, month=month).exists():
        raise BusinessRuleError(f"A competência {month:02d}/{year} já existe.")
    return Competence.objects.create(
        institution=institution, fiscal_year=fy, year=year, month=month
    )


@transaction.atomic
def close_competence(comp: Competence, user) -> Competence:
    if comp.status == CompetenceStatus.FECHADA:
        raise BusinessRuleError("A competência já está fechada.")
    comp.status = CompetenceStatus.FECHADA
    comp.closed_at = timezone.now()
    comp.closed_by = user
    comp.save()
    log_event("CLOSE", module="admin.competencias", obj=comp)
    return comp


@transaction.atomic
def reopen_competence(comp: Competence, justification: str) -> Competence:
    if comp.status != CompetenceStatus.FECHADA:
        raise BusinessRuleError("A competência não está fechada.")
    if comp.fiscal_year.status == FiscalYearStatus.FECHADO:
        raise BusinessRuleError("Reabra primeiro o exercício correspondente.")
    _require_justification(justification)
    comp.status = CompetenceStatus.ABERTA
    comp.closed_at = None
    comp.closed_by = None
    comp.save()
    log_event("REOPEN", module="admin.competencias", obj=comp, justification=justification)
    return comp


def get_parameter(institution: Institution, key: str, on: date | None = None, default=None):
    """Valor do parâmetro vigente na data informada (padrão: hoje)."""
    on = on or timezone.localdate()
    param = (
        Parameter.objects.filter(institution=institution, key=key, valid_from__lte=on)
        .exclude(valid_to__lt=on)
        .order_by("-valid_from", "-version")
        .first()
    )
    return param.value if param else default


@transaction.atomic
def set_parameter(
    institution: Institution, key: str, value, valid_from: date,
    description: str = "", change_reason: str = "",
) -> Parameter:
    """
    Cria nova versão do parâmetro. A versão vigente anterior tem sua vigência
    encerrada no dia anterior a valid_from. Versões futuras já cadastradas
    impedem a operação (evita sobreposição de vigências).
    """
    versions = Parameter.objects.select_for_update().filter(institution=institution, key=key)
    last = versions.order_by("-version").first()
    if last is not None:
        if versions.filter(valid_from__gte=valid_from).exists():
            raise BusinessRuleError(
                "Já existe versão deste parâmetro com vigência igual ou posterior à data informada."
            )
        if not change_reason.strip():
            raise BusinessRuleError("Informe o motivo da alteração do parâmetro.")
        current = versions.filter(valid_to__isnull=True).first() or versions.exclude(
            valid_to__lt=valid_from
        ).order_by("-valid_from").first()
        if current is not None:
            current.valid_to = valid_from - timedelta(days=1)
            current.save(update_fields=["valid_to", "updated_at", "updated_by"])
    return Parameter.objects.create(
        institution=institution,
        key=key,
        value=value,
        valid_from=valid_from,
        description=description or (last.description if last else ""),
        version=(last.version + 1) if last else 1,
        change_reason=change_reason,
    )


def _require_justification(text: str) -> None:
    if not text or len(text.strip()) < 10:
        raise BusinessRuleError("Informe uma justificativa com pelo menos 10 caracteres.")
