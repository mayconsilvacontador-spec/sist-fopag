"""
Cálculo da folha de ativos (por órgão e competência).

Para cada vínculo ativo do órgão no mês:
  1. dias trabalhados (mês comercial de 30 dias): admissão/desligamento no mês e licença SEM vencimento
     (histórico funcional) reduzem os dias;
  2. VENCIMENTO = tabela de vencimentos do cargo/nível vigente (ou "vencimento base" do vínculo), proporcional aos dias;
  3. ADICIONAL POR TEMPO = % do vencimento a cada N anos no ente (com limite) — regra cadastrada na rubrica;
  4. LANÇAMENTOS do vínculo (valor fixo ou % do vencimento), com parcelas;
  5. FALTAS do histórico funcional (iniciadas no mês) = dias × vencimento ÷ 30;
  6. CONTRIBUIÇÃO AO RPPS = alíquota do segurado × proventos que incidem (com previdência complementar: até o teto
     do RGPS); a PATRONAL (parâmetro arrecadacao.aliquota_patronal) é informada, não descontada;
  7. IRRF pela tabela vigente (deduções: contribuição, dependentes para IR) — mesma rotina da folha de benefícios.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.folha.engine import month_bounds, paid_days, prorate
from apps.folha.tax import ZERO, IrTable, compute_ir, q, rate_on

from .models import (
    EDITABLE, ActiveEntry, ActivePayslip, ActivePayslipItem, ActiveRubric, ActiveRun, RubricCalc, RubricKind,
    RunStatus, SalaryScale,
)

MODULE = "ativos.folha"
DEFAULT_RUBRICS = [  # sugestão inicial — cada órgão ajusta ao seu estatuto
    ("1001", "VENCIMENTO", "PROVENTO", "VENCIMENTO", True, True, {}),
    ("1002", "ADICIONAL POR TEMPO DE SERVIÇO", "PROVENTO", "ADICIONAL_TEMPO", True, True,
     {"percent": "5", "period_years": 3, "max_percent": "60",
      "legal_basis": "Sugestão: triênio de 5% (conferir o estatuto do órgão)"}),
    ("1010", "GRATIFICAÇÃO", "PROVENTO", "LANCAMENTO", True, True, {}),
    ("1011", "FUNÇÃO GRATIFICADA", "PROVENTO", "LANCAMENTO", False, True, {}),
    ("1012", "HORAS EXTRAS", "PROVENTO", "LANCAMENTO", False, True, {}),
    ("1013", "INSALUBRIDADE", "PROVENTO", "LANCAMENTO", True, True, {}),
    ("1014", "AUXÍLIO-ALIMENTAÇÃO (indenizatório)", "PROVENTO", "LANCAMENTO", False, False, {}),
    ("2001", "CONTRIBUIÇÃO AO RPPS", "DESCONTO", "CONTRIB_RPPS", False, False, {}),
    ("2002", "IRRF", "DESCONTO", "IRRF", False, False, {}),
    ("2003", "FALTAS", "DESCONTO", "FALTAS", True, True, {}),
    ("2010", "CONSIGNAÇÃO", "DESCONTO", "LANCAMENTO", False, False, {}),
    ("2011", "PENSÃO ALIMENTÍCIA", "DESCONTO", "LANCAMENTO", False, False, {}),
    ("2012", "DESCONTOS DIVERSOS", "DESCONTO", "LANCAMENTO", False, False, {}),
]


def _justify(text: str):
    if not text or len(text.strip()) < 10:
        raise BusinessRuleError("Informe uma justificativa com pelo menos 10 caracteres.")


def ensure_default_rubrics(institution) -> int:
    if ActiveRubric.objects.filter(institution=institution).exists():
        return 0
    for code, name, kind, calc, rpps, ir, extra in DEFAULT_RUBRICS:
        ActiveRubric.objects.create(institution=institution, code=code, name=name, kind=kind, calc=calc,
                                    inc_rpps=rpps if kind == "PROVENTO" or calc == "FALTAS" else False, inc_ir=ir, **extra)
    return len(DEFAULT_RUBRICS)


def validate_rubric(r: ActiveRubric):
    if r.calc in (RubricCalc.CONTRIB_RPPS, RubricCalc.IRRF, RubricCalc.FALTAS) and r.kind != RubricKind.DESCONTO:
        raise BusinessRuleError("Contribuição, IRRF e faltas são rubricas de desconto.")
    if r.calc in (RubricCalc.VENCIMENTO, RubricCalc.ADICIONAL_TEMPO) and r.kind != RubricKind.PROVENTO:
        raise BusinessRuleError("Vencimento e adicional por tempo são rubricas de provento.")
    if r.calc == RubricCalc.ADICIONAL_TEMPO and not (r.percent and r.period_years):
        raise BusinessRuleError("Adicional por tempo exige o percentual e o período (anos).")
    if r.calc != RubricCalc.LANCAMENTO and r.active:
        dup = ActiveRubric.objects.filter(institution=r.institution, calc=r.calc, active=True).exclude(pk=r.pk)
        if r.calc != RubricCalc.ADICIONAL_TEMPO and dup.exists():
            raise BusinessRuleError(f"Já existe rubrica ativa com o cálculo '{r.get_calc_display()}' ({dup.first().code}).")


def validate_entry(e: ActiveEntry):
    if e.rubric.calc != RubricCalc.LANCAMENTO:
        raise BusinessRuleError(f"A rubrica {e.rubric.code} é calculada automaticamente e não aceita lançamentos.")
    if (e.amount is None) == (e.percent is None):
        raise BusinessRuleError("Informe o valor OU o percentual do vencimento.")
    if (e.amount is not None and e.amount <= 0) or (e.percent is not None and not 0 < e.percent <= 300):
        raise BusinessRuleError("Valor ou percentual inválido.")
    e.start = e.start.replace(day=1)
    if e.end:
        e.end = e.end.replace(day=1)
        if e.end < e.start:
            raise BusinessRuleError("A competência final não pode ser anterior à inicial.")


# ================================================================== cálculo
def scale_for(link, on: date) -> tuple[Decimal | None, str]:
    qs = (SalaryScale.objects.filter(institution=link.institution, position=link.position, valid_from__lte=on)
          .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on)))
    level = (link.class_level or "").strip()
    row = (qs.filter(level__iexact=level).order_by("-valid_from").first() if level else None) or \
        qs.filter(level="").order_by("-valid_from").first()
    if row:
        return row.amount, f"tabela {row.position.name}{' ' + row.level if row.level else ''} desde {row.valid_from:%m/%Y}"
    if link.base_salary:
        return link.base_salary, "vencimento base do vínculo"
    return None, ""


def _overlap(a0, a1, b0, b1) -> int:
    lo, hi = max(a0, b0), min(a1 or b1, b1)
    return max(0, (hi - lo).days + 1)


class _Slip:
    def __init__(self, link):
        self.link, self.items, self.warnings, self.memory = link, [], [], {}

    def add(self, rubric, amount, reference="", entry=None):
        amount = q(amount)
        if amount > 0:
            self.items.append((rubric, amount, reference, entry))

    def total(self, kind, attr=None):
        return sum((a for r, a, _, _ in self.items if r.kind == kind and (attr is None or getattr(r, attr))), ZERO)


def _links(run):
    from apps.employment.models import EmploymentLink

    m0, m1 = month_bounds(run.year, run.month)
    return (EmploymentLink.objects.filter(institution=run.institution, organ=run.organ, position_start__lte=m1)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=m0)).filter(Q(status="ATIVO") | Q(end_date__gte=m0))
            .select_related("person", "position").order_by("person__name"))


def calculate_link(run, link, rubrics: dict, ctx: dict) -> _Slip:
    from apps.employment.models import EventType
    from apps.people.models import Dependency

    m0, m1 = ctx["m0"], ctx["m1"]
    s = _Slip(link)
    start = max(link.position_start, link.ente_start)
    days = paid_days(start, link.end_date, m0, m1)
    unpaid = 0
    for ev in link.events.filter(event_type__in=[EventType.LICENCA, EventType.AFASTAMENTO, EventType.SUSPENSAO],
                                 with_pay=False, start_date__lte=m1).filter(Q(end_date__isnull=True) | Q(end_date__gte=m0)):
        unpaid += _overlap(ev.start_date, ev.end_date, m0, m1)
    days = max(0, days - min(unpaid, 30))
    s.memory["dias"] = {"trabalhados": days, "licenca_sem_vencimento": unpaid}
    base, origin = scale_for(link, m0)
    if base is None:
        s.warnings.append("Cargo/nível sem valor na tabela de vencimentos e sem vencimento base no vínculo.")
        base = ZERO
    venc = prorate(base, days)
    s.memory["vencimento"] = {"integral": str(base), "origem": origin, "proporcional": str(venc)}
    if (r := rubrics.get(RubricCalc.VENCIMENTO)):
        s.add(r, venc, f"{days} dias")
    # adicional(is) por tempo de serviço no ente
    for r in rubrics.get("ADICIONAIS", []):
        years = (m1 - link.ente_start).days // 365
        periods = years // r.period_years
        pct = min(r.percent * periods, r.max_percent or Decimal("999"))
        if pct > 0:
            s.add(r, venc * pct / 100, f"{pct:g}%")
            s.memory.setdefault("adicional_tempo", []).append({"anos": years, "percentual": str(pct)})
    # lançamentos do vínculo
    for e in (ActiveEntry.objects.filter(link=link, active=True, start__lte=m0).filter(Q(end__isnull=True) | Q(end__gte=m0))
              .select_related("rubric")):
        if not e.rubric.active:
            continue
        if e.installments and e.paid_installments >= e.installments:
            continue
        value = e.amount if e.amount is not None else venc * e.percent / 100
        ref = f"{e.paid_installments + 1}/{e.installments}" if e.installments else (f"{e.percent:g}%" if e.percent else "")
        s.add(e.rubric, value, ref, e)
    # faltas não abonadas (histórico funcional) iniciadas no mês
    if (r := rubrics.get(RubricCalc.FALTAS)):
        faltas = sum(ev.days or 0 for ev in link.events.filter(event_type=EventType.FALTAS, start_date__gte=m0,
                                                                start_date__lte=m1))
        if faltas:
            s.add(r, base / 30 * faltas, f"{faltas} dia(s)")
    # contribuição ao RPPS (descontos que incidem, como faltas, reduzem a base)
    base_rpps = max(ZERO, s.total(RubricKind.PROVENTO, "inc_rpps") - s.total(RubricKind.DESCONTO, "inc_rpps"))
    teto = None
    if link.complementary_pension:
        teto = ctx["teto"]
        base_rpps = min(base_rpps, teto)
    contrib = q(base_rpps * ctx["rate"])
    if (r := rubrics.get(RubricCalc.CONTRIB_RPPS)) and contrib > 0:
        s.add(r, contrib, f"{ctx['rate'] * 100:g}%")
    s.memory["rpps"] = {"base": str(base_rpps), "aliquota": str(ctx["rate"]), "contribuicao": str(contrib),
                        "limitada_ao_teto": str(teto) if teto else None,
                        "patronal": str(q(base_rpps * ctx["patronal"]))}
    s.rpps_base, s.employer = base_rpps, q(base_rpps * ctx["patronal"])
    # IRRF
    taxable = max(ZERO, s.total(RubricKind.PROVENTO, "inc_ir") - s.total(RubricKind.DESCONTO, "inc_ir"))
    alimony = sum((a for r, a, _, _ in s.items if r.kind == "DESCONTO" and "ALIMENT" in r.name.upper()), ZERO)
    deps = (Dependency.objects.filter(holder=link.person, tax_dependent=True, start_date__lte=m1)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=m0)).count())
    ir = compute_ir(ctx["ir"], taxable=taxable, pension_income=ZERO, contribution=contrib, dependents=deps,
                    alimony=alimony, over_65=False, molestia=False)
    if (r := rubrics.get(RubricCalc.IRRF)) and ir.tax > 0:
        s.add(r, ir.tax, f"{ir.rate * 100:g}%")
    s.memory["irrf"] = {**ir.as_dict(), "rendimento_tributavel": str(taxable), "dependentes": deps}
    s.ir_base = ir.base
    gross, disc = s.total(RubricKind.PROVENTO), s.total(RubricKind.DESCONTO)
    if gross - disc < 0:
        s.warnings.append("Líquido negativo — revise os descontos.")
    return s


@transaction.atomic
def open_run(institution, *, organ, year: int, month: int) -> ActiveRun:
    if organ.institution_id != institution.pk:
        raise BusinessRuleError("Órgão inválido.")
    if not (1 <= month <= 12 and 2000 <= year <= 2100):
        raise BusinessRuleError("Competência inválida.")
    if ActiveRun.objects.filter(institution=institution, organ=organ, year=year, month=month).exists():
        raise BusinessRuleError(f"A folha de {month:02d}/{year} de {organ.name} já existe.")
    pending = ActiveRun.objects.filter(institution=institution, organ=organ, status__in=EDITABLE).first()
    if pending:
        raise BusinessRuleError(f"Feche antes a folha {pending.month:02d}/{pending.year} deste órgão.")
    ensure_default_rubrics(institution)
    run = ActiveRun.objects.create(institution=institution, organ=organ, year=year, month=month)
    log_event("CREATE", module=MODULE, obj=run, object_repr=str(run))
    return run


@transaction.atomic
def calculate(run: ActiveRun) -> ActiveRun:
    from apps.concessao.services import rgps_ceiling
    from apps.folha.services import _bank_snapshot
    from apps.institutions.services import get_parameter

    run = ActiveRun.objects.select_for_update().get(pk=run.pk)
    if run.status not in EDITABLE:
        raise BusinessRuleError("Folha fechada não pode ser recalculada. Reabra-a (com justificativa).")
    m0, m1 = month_bounds(run.year, run.month)
    rubs = list(ActiveRubric.objects.filter(institution=run.institution, active=True))
    rubrics = {r.calc: r for r in rubs if r.calc not in (RubricCalc.LANCAMENTO, RubricCalc.ADICIONAL_TEMPO)}
    rubrics["ADICIONAIS"] = [r for r in rubs if r.calc == RubricCalc.ADICIONAL_TEMPO]
    for needed in (RubricCalc.VENCIMENTO, RubricCalc.CONTRIB_RPPS, RubricCalc.IRRF):
        if needed not in rubrics:
            raise BusinessRuleError(f"Cadastre/ative a rubrica de '{RubricCalc(needed).label}' (Folha de Ativos › Rubricas).")
    teto, warn = rgps_ceiling(run.institution, m0)
    patronal = Decimal(str(get_parameter(run.institution, "arrecadacao.aliquota_patronal", m0, default="0") or 0))
    ctx = {"m0": m0, "m1": m1, "rate": rate_on(run.institution, m0), "ir": IrTable.load(run.institution, m0),
           "teto": teto, "patronal": patronal}
    run.payslips.all().delete()
    totals = {"servidores": 0, "proventos": ZERO, "descontos": ZERO, "liquido": ZERO, "contribuicao_servidor": ZERO,
              "contribuicao_patronal": ZERO, "base_rpps": ZERO, "irrf": ZERO, "sem_conta": 0, "por_massa": {}}
    warnings = list(warn)
    for link in _links(run):
        s = calculate_link(run, link, rubrics, ctx)
        bank = _bank_snapshot(link.person, m1)
        if not bank:
            s.warnings.append("Servidor sem conta bancária vigente.")
            totals["sem_conta"] += 1
        gross, disc = s.total(RubricKind.PROVENTO), s.total(RubricKind.DESCONTO)
        slip = ActivePayslip.objects.create(
            institution=run.institution, run=run, link=link, person=link.person, registration=link.registration,
            position_name=link.position.name, segment=link.segment, days=s.memory["dias"]["trabalhados"],
            gross=gross, discounts=disc, net=gross - disc, rpps_base=s.rpps_base, employer_contribution=s.employer,
            ir_base=s.ir_base, bank=bank, memory=s.memory, warnings=s.warnings)
        ActivePayslipItem.objects.bulk_create([
            ActivePayslipItem(institution=run.institution, payslip=slip, rubric=r, source_entry=e, code=r.code,
                              name=r.name[:120], kind=r.kind, reference=ref[:30], amount=a)
            for r, a, ref, e in s.items])
        contrib = sum((a for r, a, _, _ in s.items if r.calc == RubricCalc.CONTRIB_RPPS), ZERO)
        irrf = sum((a for r, a, _, _ in s.items if r.calc == RubricCalc.IRRF), ZERO)
        totals["servidores"] += 1
        totals["proventos"] += gross
        totals["descontos"] += disc
        totals["liquido"] += gross - disc
        totals["contribuicao_servidor"] += contrib
        totals["contribuicao_patronal"] += s.employer
        totals["base_rpps"] += s.rpps_base
        totals["irrf"] += irrf
        pm = totals["por_massa"].setdefault(link.segment, {"servidores": 0, "base_rpps": ZERO, "servidor": ZERO,
                                                           "patronal": ZERO})
        pm["servidores"] += 1
        pm["base_rpps"] += s.rpps_base
        pm["servidor"] += contrib
        pm["patronal"] += s.employer
    if not totals["servidores"]:
        warnings.append("Nenhum servidor ativo neste órgão na competência.")
    run.totals = _jsonable(totals)
    run.warnings = warnings
    run.status, run.calculated_at, run.checked_by, run.checked_at = RunStatus.CALCULADA, timezone.now(), None, None
    run.save()
    log_event("UPDATE", module=MODULE, obj=run, object_repr=f"{run} — cálculo",
              extra={"servidores": totals["servidores"], "liquido": str(totals["liquido"])})
    return run


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return str(v) if isinstance(v, Decimal) else v


@transaction.atomic
def check(run: ActiveRun, user) -> ActiveRun:
    if run.status != RunStatus.CALCULADA:
        raise BusinessRuleError("Só é possível conferir uma folha calculada.")
    run.status, run.checked_by, run.checked_at = RunStatus.CONFERIDA, user, timezone.now()
    run.save(update_fields=["status", "checked_by", "checked_at", "updated_at"])
    log_event("UPDATE", module=MODULE, obj=run, object_repr=f"{run} — conferência")
    return run


@transaction.atomic
def close(run: ActiveRun, user) -> ActiveRun:
    run = ActiveRun.objects.select_for_update().get(pk=run.pk)
    if run.status != RunStatus.CONFERIDA:
        raise BusinessRuleError("A folha precisa estar conferida para ser fechada.")
    effects = []
    for item in ActivePayslipItem.objects.filter(payslip__run=run, source_entry__isnull=False).select_related("source_entry"):
        e = item.source_entry
        if e.installments:
            e.paid_installments += 1
            e.save(update_fields=["paid_installments", "updated_at"])
            effects.append(str(e.pk))
    run.status, run.closed_by, run.closed_at, run.close_effects = RunStatus.FECHADA, user, timezone.now(), {"parcelas": effects}
    run.save(update_fields=["status", "closed_by", "closed_at", "close_effects", "updated_at"])
    log_event("CLOSE", module=MODULE, obj=run, object_repr=str(run))
    return run


@transaction.atomic
def reopen(run: ActiveRun, justification: str) -> ActiveRun:
    run = ActiveRun.objects.select_for_update().get(pk=run.pk)
    if run.status != RunStatus.FECHADA:
        raise BusinessRuleError("Só folhas fechadas podem ser reabertas.")
    _justify(justification)
    later = ActiveRun.objects.filter(institution=run.institution, organ=run.organ).filter(
        Q(year__gt=run.year) | Q(year=run.year, month__gt=run.month)).exclude(status=RunStatus.ABERTA).first()
    if later:
        raise BusinessRuleError(f"Existe folha posterior já calculada ({later.month:02d}/{later.year}). Reabra-a antes.")
    for pk in (run.close_effects or {}).get("parcelas", []):
        e = ActiveEntry.objects.filter(pk=pk).first()
        if e:
            e.paid_installments = max(0, e.paid_installments - 1)
            e.save(update_fields=["paid_installments", "updated_at"])
    run.status, run.closed_by, run.closed_at, run.close_effects = RunStatus.CONFERIDA, None, None, {}
    run.save(update_fields=["status", "closed_by", "closed_at", "close_effects", "updated_at"])
    log_event("REOPEN", module=MODULE, obj=run, object_repr=str(run), justification=justification)
    return run


@transaction.atomic
def delete_run(run: ActiveRun, justification: str) -> None:
    run = ActiveRun.objects.select_for_update().get(pk=run.pk)
    if run.status not in EDITABLE:
        raise BusinessRuleError("Folha fechada não pode ser excluída (reabra-a antes, com justificativa).")
    _justify(justification)
    log_event("DELETE", module=MODULE, obj=run, object_repr=f"{run} — exclusão", justification=justification.strip(),
              extra={"totais": run.totals or {}})
    run.delete()


@transaction.atomic
def new_scale(institution, *, position, level: str, amount, valid_from: date, legal_basis: str = "") -> SalaryScale:
    """Reajuste: nova vigência; a anterior (mesmo cargo/nível) é encerrada no dia anterior. Nada é apagado."""
    amount = q(amount)
    if amount <= 0:
        raise BusinessRuleError("Valor do vencimento inválido.")
    level = (level or "").strip().upper()
    cur = (SalaryScale.objects.select_for_update().filter(institution=institution, position=position, level=level,
                                                          valid_to__isnull=True).first())
    if cur:
        if valid_from <= cur.valid_from:
            raise BusinessRuleError(f"A nova vigência deve começar depois de {cur.valid_from:%d/%m/%Y} (vigência atual).")
        cur.valid_to = valid_from - timedelta(days=1)
        cur.save(update_fields=["valid_to", "updated_at"])
    s = SalaryScale.objects.create(institution=institution, position=position, level=level, amount=amount,
                                   valid_from=valid_from, legal_basis=legal_basis[:200])
    log_event("CREATE", module="ativos.vencimentos", obj=s,
              object_repr=f"Vencimento {position.name} {level} = {amount} desde {valid_from:%d/%m/%Y}")
    return s


