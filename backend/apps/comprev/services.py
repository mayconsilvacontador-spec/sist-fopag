"""Regras do controle do COMPREV: requerimentos, situação, valor mensal com vigência, recebimentos/pagamentos e fluxo."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import is_valid_cnpj, only_digits
from apps.financeiro.services import add_months, month_start, q

from .models import (
    COMPENSATING, NEEDS_REASON, TRANSITIONS, BenefitKind, ComprevProcess, Counterpart, Direction, MonthlyValue,
    Movement, MovementKind, ProcessEvent, Status,
)

ZERO = Decimal("0.00")
MODULE = {Direction.RECEBER: "comprev.recebimentos", Direction.PAGAR: "comprev.pagamentos"}


def _justify(text: str, what="o motivo"):
    if not text or len(text.strip()) < 10:
        raise BusinessRuleError(f"Informe {what} com pelo menos 10 caracteres.")


# ================================================================== requerimentos
def validate_process(p: ComprevProcess):
    p.counterpart_cnpj = only_digits(p.counterpart_cnpj)
    if p.counterpart_cnpj and not is_valid_cnpj(p.counterpart_cnpj):
        raise BusinessRuleError("CNPJ do outro regime inválido.")
    if p.counterpart_kind == Counterpart.RPPS and not p.counterpart_cnpj:
        raise BusinessRuleError("Informe o CNPJ do outro RPPS.")
    if p.counterpart_kind == Counterpart.RGPS and not p.counterpart_name:
        p.counterpart_name = "Instituto Nacional do Seguro Social — INSS"
    if p.direction == Direction.RECEBER:
        if p.ctc_id:
            raise BusinessRuleError("CTC emitida por nós só se usa nos requerimentos A PAGAR.")
        if p.benefit_id:
            b = p.benefit
            owner = b.instituidor_id if b.kind == "PENSAO" else b.beneficiary_id
            if owner != p.person_id:
                raise BusinessRuleError("O benefício escolhido não é deste segurado (na pensão, informe o instituidor).")
            p.benefit_kind = BenefitKind.PENSAO if b.kind == "PENSAO" else BenefitKind.APOSENTADORIA
            p.plan = b.payroll_group.plan  # segregação: o plano é o da folha que paga o benefício
            p.benefit_start = p.benefit_start or b.start_date
        if p.averbacao_id and p.averbacao.person_id != p.person_id:
            raise BusinessRuleError("A averbação escolhida não é deste segurado.")
    else:
        if p.benefit_id or p.averbacao_id:
            raise BusinessRuleError("Nos requerimentos A PAGAR o benefício é do outro regime: informe a CTC, não o benefício.")
        if p.ctc_id and p.ctc.person_id != p.person_id:
            raise BusinessRuleError("A CTC escolhida não é deste segurado.")
    if p.plan_id is None:
        raise BusinessRuleError("Informe o plano (Financeiro ou Previdenciário).")
    if not p.benefit_kind:
        raise BusinessRuleError("Informe o tipo de benefício (aposentadoria ou pensão).")
    if p.origin_days and p.total_days and p.origin_days > p.total_days:
        raise BusinessRuleError("O tempo no regime de origem não pode ser maior que o tempo total.")
    if p.requested_at and p.requested_at > timezone.localdate():
        raise BusinessRuleError("A data do requerimento não pode ser futura.")
    return p


def suggested_value(p: ComprevProcess) -> Decimal | None:
    """Pro rata (Lei 9.796/1999, art. 4º): renda mensal inicial × tempo no regime de origem ÷ tempo total. Só sugestão:
    o valor que vale é o deferido no COMPREV (pode ser limitado ao que o regime de origem pagaria)."""
    if not (p.rmi and p.origin_days and p.total_days):
        return None
    return q(p.rmi * p.origin_days / p.total_days)


def value_at(p: ComprevProcess, comp: date) -> Decimal | None:
    v = p.values.filter(valid_from__lte=month_start(comp)).order_by("-valid_from").first()
    return v.amount if v else None


def current_value(p: ComprevProcess) -> Decimal | None:
    v = p.values.order_by("-valid_from").first()
    return v.amount if v else None


@transaction.atomic
def change_status(p: ComprevProcess, new: str, *, when: date, note: str = "", comp_start: date | None = None,
                  amount=None, backlog=None, requirement_due: date | None = None, ended_at: date | None = None):
    p = ComprevProcess.objects.select_for_update().get(pk=p.pk)
    if new not in TRANSITIONS.get(p.status, set()):
        raise BusinessRuleError(f"Não é possível passar de '{p.get_status_display()}' para '{Status(new).label}'.")
    if when > timezone.localdate():
        raise BusinessRuleError("A data não pode ser futura.")
    if new in NEEDS_REASON:
        _justify(note)
    if new == Status.ENVIADO and not p.request_number:
        raise BusinessRuleError("Informe o nº do requerimento no COMPREV antes de marcar como enviado.")
    if new == Status.EXIGENCIA:
        _justify(note, "a exigência")
        if requirement_due is None:
            raise BusinessRuleError("Informe o prazo para cumprir a exigência.")
        p.requirement_text, p.requirement_due = note.strip(), requirement_due
    if p.status == Status.EXIGENCIA and new != Status.EXIGENCIA:
        p.requirement_due = None
    if new == Status.DEFERIDO:
        if comp_start is None or amount in (None, ""):
            raise BusinessRuleError("Informe o início da compensação e o valor mensal deferido.")
        amount = q(amount)
        if amount <= 0:
            raise BusinessRuleError("Valor mensal deferido inválido.")
        p.comp_start = month_start(comp_start)
        p.backlog_amount = q(backlog or 0)
        MonthlyValue.objects.create(institution=p.institution, process=p, valid_from=p.comp_start, amount=amount,
                                    reason="Valor deferido")
    if new == Status.CESSADO:
        ended = ended_at or when
        if ended < p.comp_start:
            raise BusinessRuleError("O fim da compensação não pode ser anterior ao início.")
        p.ended_at = month_start(ended)
    if new in NEEDS_REASON:
        p.decision_reason = note.strip()
    ProcessEvent.objects.create(institution=p.institution, process=p, date=when, status_from=p.status, status_to=new,
                                note=note.strip())
    old = p.status
    p.status, p.status_date = new, when
    p.save()
    log_event("UPDATE", module="comprev.processos", obj=p, object_repr=f"{p} — {Status(old).label} → {Status(new).label}",
              justification=note.strip() or None)
    return p


@transaction.atomic
def add_value(p: ComprevProcess, valid_from: date, amount, reason: str) -> MonthlyValue:
    if p.status != Status.DEFERIDO:
        raise BusinessRuleError("Só requerimentos deferidos têm valor mensal.")
    _justify(reason)
    valid_from = month_start(valid_from)
    last = p.values.order_by("-valid_from").first()
    if last and valid_from <= last.valid_from:
        raise BusinessRuleError(f"O novo valor deve valer a partir de uma competência posterior a "
                                f"{last.valid_from:%m/%Y} (o histórico não é sobrescrito).")
    amount = q(amount)
    if amount <= 0:
        raise BusinessRuleError("Valor inválido.")
    v = MonthlyValue.objects.create(institution=p.institution, process=p, valid_from=valid_from, amount=amount,
                                    reason=reason.strip()[:200])
    log_event("UPDATE", module="comprev.processos", obj=p, object_repr=f"{p} — novo valor {amount} a partir de "
              f"{valid_from:%m/%Y}", justification=reason.strip())
    return v


# ================================================================== recebimentos e pagamentos
def _in_period(p: ComprevProcess, comp: date) -> bool:
    return bool(p.comp_start and p.comp_start <= comp and (p.ended_at is None or comp <= p.ended_at))


@transaction.atomic
def register(p: ComprevProcess, *, kind: str, competence: date, amount, when: date, document: str = "",
             expected=None) -> Movement:
    if p.status not in COMPENSATING:
        raise BusinessRuleError("Só há valores a registrar em requerimento deferido (ou cessado, para acertos).")
    comp, amount = month_start(competence), q(amount)
    if amount <= 0:
        raise BusinessRuleError("Informe o valor.")
    if when > timezone.localdate():
        raise BusinessRuleError("A data do crédito/pagamento não pode ser futura.")
    if kind == MovementKind.MENSAL:
        if not _in_period(p, comp):
            raise BusinessRuleError(f"A competência {comp:%m/%Y} está fora do período da compensação.")
        if p.movements.filter(kind=MovementKind.MENSAL, competence=comp, active=True).exists():
            raise BusinessRuleError(f"O fluxo de {comp:%m/%Y} deste requerimento já foi registrado. "
                                    "Para diferença, use 'Ajuste' ou 'Glosa'.")
        expected = value_at(p, comp) if expected is None else expected
    m = Movement.objects.create(institution=p.institution, process=p, plan=p.plan, direction=p.direction, kind=kind,
                                competence=comp, expected=expected, amount=amount, date=when, document=document[:60])
    log_event("CREATE", module=MODULE[p.direction], obj=m,
              object_repr=f"{p} — {m.get_kind_display()} {comp:%m/%Y}", extra={"valor": str(amount)})
    return m


@transaction.atomic
def register_batch(institution, direction: str, competence: date, when: date, document: str,
                   items: list[dict]) -> list[Movement]:
    """Fluxo do mês em lote (o COMPREV credita/debita um valor só por competência). items: [{process, amount}]."""
    if not items:
        raise BusinessRuleError("Nenhum requerimento selecionado.")
    out = []
    for it in items:
        p = ComprevProcess.objects.filter(institution=institution, direction=direction, pk=it.get("process")).first()
        if p is None:
            raise BusinessRuleError("Requerimento inválido na lista.")
        out.append(register(p, kind=MovementKind.MENSAL, competence=competence, amount=it.get("amount"), when=when,
                            document=document))
    return out


@transaction.atomic
def reverse(m: Movement, reason: str) -> Movement:
    _justify(reason)
    if not m.active:
        raise BusinessRuleError("Lançamento já estornado.")
    if m.revenue_id and m.revenue.active:
        raise BusinessRuleError("Este recebimento já virou receita no Financeiro: estorne a receita antes.")
    m.active, m.reversal_reason = False, reason.strip()
    m.save(update_fields=["active", "reversal_reason", "updated_at"])
    log_event("UPDATE", module=MODULE[m.direction], obj=m, object_repr=f"Estorno — {m.process} {m.competence:%m/%Y}",
              justification=reason.strip())
    return m


@transaction.atomic
def to_revenue(institution, ids: list, account=None):
    """Leva recebimentos ao Financeiro como UMA receita (tipo COMPREV) por plano e data de crédito."""
    from apps.financeiro.models import Revenue, RevenueKind

    ms = list(Movement.objects.select_for_update().filter(institution=institution, pk__in=ids)
              .select_related("plan", "process"))
    if not ms or len(ms) != len(set(ids)):
        raise BusinessRuleError("Selecione os recebimentos.")
    if any(m.direction != Direction.RECEBER or not m.active or m.revenue_id for m in ms):
        raise BusinessRuleError("Só recebimentos ativos que ainda não viraram receita.")
    plans, dates = {m.plan_id for m in ms}, {m.date for m in ms}
    if len(plans) > 1 or len(dates) > 1:
        raise BusinessRuleError("Selecione recebimentos do mesmo plano e da mesma data de crédito.")
    plan = ms[0].plan
    if account is not None and account.plan_id != plan.pk:
        raise BusinessRuleError(f"Segregação de massas: receita do plano {plan.code} não pode ser creditada na conta "
                                f"do plano {account.plan.code}.")
    total = sum((m.signed for m in ms), ZERO)
    if total <= 0:
        raise BusinessRuleError("O total selecionado (descontadas as glosas) precisa ser positivo.")
    comps = {m.competence for m in ms}
    rev = Revenue.objects.create(
        institution=institution, plan=plan, kind=RevenueKind.COMPREV, date=ms[0].date,
        competence=comps.pop() if len(comps) == 1 else None, amount=total, account=account,
        document=(ms[0].document or "COMPREV")[:60], description=f"Compensação previdenciária — {len(ms)} lançamento(s)")
    Movement.objects.filter(pk__in=[m.pk for m in ms]).update(revenue=rev)
    log_event("CREATE", module="arrecadacao.receitas", obj=rev, object_repr=f"Receita — {rev.description}",
              extra={"valor": str(total), "origem": "COMPREV"})
    return rev


# ================================================================== fluxo e indicadores
def flow(institution, comp: date, direction: str | None = None) -> dict:
    """Previsto (valor vigente dos deferidos) × realizado (fluxo mensal + ajustes − glosas) na competência."""
    comp = month_start(comp)
    procs = (ComprevProcess.objects.filter(institution=institution, status__in=COMPENSATING, comp_start__lte=comp)
             .filter(Q(ended_at__isnull=True) | Q(ended_at__gte=comp)).select_related("person", "plan"))
    if direction:
        procs = procs.filter(direction=direction)
    moves = defaultdict(lambda: ZERO)
    registered = set()
    mq = Movement.objects.filter(institution=institution, competence=comp, active=True)
    if direction:
        mq = mq.filter(direction=direction)
    for m in mq.exclude(kind=MovementKind.ATRASADOS):
        moves[m.process_id] += m.signed
        if m.kind == MovementKind.MENSAL:
            registered.add(m.process_id)
    rows, seen = [], set()
    for p in procs.order_by("direction", "person__name"):
        exp = value_at(p, comp) or ZERO
        real = moves.get(p.pk, ZERO)
        seen.add(p.pk)
        rows.append({"process": str(p.pk), "direction": p.direction, "person": p.person.name, "plan": p.plan.code,
                     "counterpart": p.counterpart_name, "request_number": p.request_number, "expected": exp,
                     "realized": real, "difference": real - exp, "registered": p.pk in registered})
    for pid, real in moves.items():  # acertos de requerimentos fora do período (ex.: cessados)
        if pid not in seen:
            p = ComprevProcess.objects.select_related("person", "plan").get(pk=pid)
            rows.append({"process": str(p.pk), "direction": p.direction, "person": p.person.name, "plan": p.plan.code,
                         "counterpart": p.counterpart_name, "request_number": p.request_number, "expected": ZERO,
                         "realized": real, "difference": real, "registered": False})
    totals = {}
    for d in (Direction.RECEBER, Direction.PAGAR):
        rs = [r for r in rows if r["direction"] == d]
        totals[d] = {"previsto": sum((r["expected"] for r in rs), ZERO), "realizado": sum((r["realized"] for r in rs), ZERO),
                     "pendentes": sum(1 for r in rs if not r["registered"] and r["expected"] > 0)}
    backlog = (Movement.objects.filter(institution=institution, competence=comp, active=True, kind=MovementKind.ATRASADOS)
               .values("direction").order_by().annotate(t=Sum("amount")))
    for b in backlog:
        totals.setdefault(b["direction"], {})["atrasados"] = b["t"]
    return {"competencia": comp, "linhas": rows, "totais": totals,
            "saldo": totals[Direction.RECEBER]["realizado"] - totals[Direction.PAGAR]["realizado"]}


def potential(institution):
    """Benefícios ativos com tempo averbado de outro regime (marcado 'sujeito ao COMPREV') e sem requerimento A RECEBER."""
    from apps.concessao.models import Benefit
    from apps.previdencia.models import Averbacao

    asked = set(ComprevProcess.objects.filter(institution=institution, direction=Direction.RECEBER)
                .exclude(status=Status.CANCELADO).values_list("person_id", flat=True))
    with_time = set(Averbacao.objects.filter(institution=institution, active=True, comprev=True)
                    .values_list("person_id", flat=True))
    out = []
    for b in (Benefit.objects.filter(institution=institution, status="ATIVO").select_related("beneficiary", "instituidor")
              .order_by("beneficiary__name")):
        owner = b.instituidor if b.kind == "PENSAO" else b.beneficiary
        if owner and owner.pk in with_time and owner.pk not in asked:
            out.append((b, owner))
    seen, uniq = set(), []
    for b, owner in out:  # pensão com várias cotas = um requerimento só (pelo instituidor)
        if owner.pk not in seen:
            seen.add(owner.pk)
            uniq.append((b, owner))
    return uniq


def indicators(institution) -> dict:
    today = timezone.localdate()
    qs = ComprevProcess.objects.filter(institution=institution)
    by_status = {d: {s: 0 for s in Status.values} for d in Direction.values}
    for r in qs.values("direction", "status").order_by().annotate(n=Count("id")):
        by_status[r["direction"]][r["status"]] = r["n"]
    current = {d: ZERO for d in Direction.values}
    for p in qs.filter(status=Status.DEFERIDO):
        current[p.direction] += current_value(p) or ZERO
    start = add_months(month_start(today), -11)
    months = []
    agg = (Movement.objects.filter(institution=institution, active=True, competence__gte=start)
           .values("competence", "direction", "kind").order_by().annotate(t=Sum("amount")))
    table = defaultdict(lambda: ZERO)
    for a in agg:
        table[(a["competence"], a["direction"])] += -a["t"] if a["kind"] == MovementKind.GLOSA else a["t"]
    for i in range(12):
        c = add_months(start, i)
        rec, pag = table[(c, Direction.RECEBER)], table[(c, Direction.PAGAR)]
        months.append({"competencia": c, "recebido": rec, "pago": pag, "saldo": rec - pag})
    backlog = {}
    for d in Direction.values:
        deferred = qs.filter(direction=d, status__in=COMPENSATING).aggregate(t=Sum("backlog_amount"))["t"] or ZERO
        done = (Movement.objects.filter(institution=institution, direction=d, active=True, kind=MovementKind.ATRASADOS)
                .aggregate(t=Sum("amount"))["t"] or ZERO)
        backlog[d] = {"deferido": deferred, "realizado": done, "saldo": max(deferred - done, ZERO)}
    durations = [(e.date - e.process.requested_at).days for e in
                 ProcessEvent.objects.filter(institution=institution, status_to=Status.DEFERIDO).select_related("process")]
    last_comp = add_months(month_start(today), -1)
    f = flow(institution, last_comp)
    return {
        "por_situacao": by_status,
        "fluxo_mensal_vigente": current,
        "ultimos_12_meses": months,
        "atrasados": backlog,
        "exigencias_vencidas": qs.filter(status=Status.EXIGENCIA, requirement_due__lt=today).count(),
        "exigencias_15_dias": qs.filter(status=Status.EXIGENCIA, requirement_due__gte=today,
                                        requirement_due__lte=today + timedelta(days=15)).count(),
        "tempo_medio_deferimento": round(sum(durations) / len(durations)) if durations else None,
        "potencial": len(potential(institution)),
        "competencia_anterior": {"competencia": last_comp, "pendentes": {d: f["totais"][d]["pendentes"] for d in Direction.values}},
    }
