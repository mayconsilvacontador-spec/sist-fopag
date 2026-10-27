"""Regras da Gestão Financeira e da Arrecadação (Fase 7)."""
import calendar
import csv
import hashlib
import io
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from . import cnab, ofx
from .models import (
    AccountingExport, AccountingMapping, Aporte, BankFile, BatchStatus, Contribution, ContributionKind,
    Installment, InstallmentAgreement, ItemStatus, PaymentBatch, PaymentItem, Revenue, RevenueKind, StatementLine,
    TreasuryAccount,
)

CENT = Decimal("0.01")
ZERO = Decimal("0")


def q(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def _justify(text: str):
    if not text or len(text.strip()) < 10:
        raise BusinessRuleError("Informe uma justificativa com pelo menos 10 caracteres.")


# ================================================================== PAGAMENTOS
@transaction.atomic
def create_batch(run, account: TreasuryAccount, payment_date: date) -> PaymentBatch:
    """Lote com os líquidos da folha FECHADA que ainda não foram pagos nem estão em outro lote em andamento."""
    from apps.folha.models import RunStatus

    if run.status != RunStatus.FECHADA:
        raise BusinessRuleError("O lote de pagamento é gerado a partir de folha FECHADA (e ainda não paga).")
    plan = run.payroll_group.plan
    if account.plan_id != plan.pk:
        raise BusinessRuleError(f"Segregação de massas: a folha {run.payroll_group.code} é paga pela conta do plano "
                                f"{plan.code}. A conta escolhida é do plano {account.plan.code}.")
    if not account.active:
        raise BusinessRuleError("Conta bancária inativa.")
    busy = PaymentItem.objects.filter(payroll_entry__run=run).exclude(status=ItemStatus.REJEITADO) \
        .exclude(batch__status=BatchStatus.CANCELADO).values_list("payroll_entry_id", flat=True)
    entries = run.entries.filter(net__gt=0).exclude(pk__in=list(busy)).select_related("beneficiary")
    last = PaymentBatch.objects.filter(institution=run.institution).order_by("-number").first()
    batch = PaymentBatch.objects.create(institution=run.institution, payroll_run=run, plan=plan, account=account,
                                        number=(last.number + 1) if last else 1, payment_date=payment_date)
    skipped, total, n = [], ZERO, 0
    for e in entries:
        if not e.bank:
            skipped.append(e.beneficiary.name)
            continue
        n += 1
        PaymentItem.objects.create(institution=run.institution, batch=batch, payroll_entry=e, beneficiary=e.beneficiary,
                                   our_number=f"L{batch.number}I{n}"[:20], bank=e.bank, amount=e.net)
        total += e.net
    if n == 0:
        raise BusinessRuleError("Nenhum pagamento a incluir (todos já estão em lote ou sem conta bancária).")
    batch.total, batch.items_count = total, n
    batch.notes = ("Sem conta bancária (fora do lote): " + ", ".join(skipped)) if skipped else ""
    batch.save()
    log_event("CREATE", module="financeiro.pagamentos", obj=batch, object_repr=str(batch),
              extra={"itens": n, "total": str(total)})
    return batch


@transaction.atomic
def approve_batch(batch: PaymentBatch, user) -> PaymentBatch:
    if batch.status != BatchStatus.RASCUNHO:
        raise BusinessRuleError("Só lotes em rascunho podem ser aprovados.")
    batch.status, batch.approved_by, batch.approved_at = BatchStatus.APROVADO, user, timezone.now()
    batch.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    log_event("UPDATE", module="financeiro.pagamentos", obj=batch, object_repr=f"{batch} — aprovação")
    return batch


@transaction.atomic
def cancel_batch(batch: PaymentBatch, justification: str) -> PaymentBatch:
    _justify(justification)
    if batch.status not in (BatchStatus.RASCUNHO, BatchStatus.APROVADO):
        raise BusinessRuleError("Lote com arquivo gerado não é cancelado: processe o retorno do banco.")
    batch.status = BatchStatus.CANCELADO
    batch.save(update_fields=["status", "updated_at"])
    log_event("UPDATE", module="financeiro.pagamentos", obj=batch, object_repr=f"{batch} — cancelamento",
              justification=justification)
    return batch


@transaction.atomic
def generate_remittance(batch: PaymentBatch) -> BankFile:
    if batch.status != BatchStatus.APROVADO:
        raise BusinessRuleError("O arquivo só é gerado para lote APROVADO.")
    acc = TreasuryAccount.objects.select_for_update().select_related("bank").get(pk=batch.account_id)
    inst = batch.institution
    if not inst.cnpj:
        raise BusinessRuleError("Cadastre o CNPJ da instituição (Administração › Instituição).")
    items = list(batch.items.filter(status=ItemStatus.PENDENTE).select_related("beneficiary"))
    payees = [cnab.Payee(our_number=i.our_number, name=i.beneficiary.name, cpf=i.beneficiary.cpf,
                         bank=i.bank.get("banco", ""), branch=i.bank.get("agencia", ""),
                         branch_digit=i.bank.get("agencia_dv", ""), account=i.bank.get("conta", ""),
                         account_digit=i.bank.get("conta_dv", ""), amount=i.amount) for i in items]
    content, summary = cnab.remessa(
        bank_code=acc.bank.code, cnpj=inst.cnpj, agreement=acc.agreement, branch=acc.branch,
        branch_digit=acc.branch_digit, account=acc.account, account_digit=acc.account_digit, company=inst.name,
        bank_name=acc.bank.name, nsa=acc.next_nsa, payment_date=batch.payment_date, payees=payees,
        service=acc.cnab_service, file_version=acc.cnab_file_version, batch_version=acc.cnab_batch_version)
    f = BankFile.objects.create(institution=inst, account=acc, kind="REMESSA", batch=batch, nsa=acc.next_nsa,
                                file_name=f"REM{acc.bank.code}_{batch.number:05d}_{acc.next_nsa:06d}.rem",
                                content=content, sha256=sha(content), summary=summary)
    acc.next_nsa += 1
    acc.save(update_fields=["next_nsa", "updated_at"])
    batch.items.filter(status=ItemStatus.PENDENTE).update(status=ItemStatus.ENVIADO)
    batch.status = BatchStatus.ARQUIVO_GERADO
    batch.save(update_fields=["status", "updated_at"])
    log_event("EXPORT", module="financeiro.arquivos_bancarios", obj=f, object_repr=f.file_name,
              extra={"sha256": f.sha256, **summary})
    return f


@transaction.atomic
def import_return(institution, account: TreasuryAccount, content: str, file_name: str) -> dict:
    rows = cnab.parse_return(content)
    if not rows:
        raise BusinessRuleError("Nenhum registro de pagamento (segmento A) encontrado no arquivo de retorno.")
    f = BankFile.objects.create(institution=institution, account=account, kind="RETORNO", file_name=file_name[:120],
                                content=content, sha256=sha(content))
    done, unknown, batches = {"PAGO": 0, "REJEITADO": 0, "AGENDADO": 0}, [], set()
    for r in rows:
        item = PaymentItem.objects.filter(institution=institution, our_number=r["our_number"],
                                          batch__account=account).first()
        if item is None:
            unknown.append(r["our_number"])
            continue
        if "00" in r["codes"]:
            item.status = ItemStatus.PAGO
            done["PAGO"] += 1
        elif r["codes"] and set(r["codes"]) <= {"BD"}:
            done["AGENDADO"] += 1
        else:
            item.status = ItemStatus.REJEITADO
            done["REJEITADO"] += 1
        item.return_code, item.return_message = ",".join(r["codes"])[:10], r["message"][:255]
        item.save(update_fields=["status", "return_code", "return_message", "updated_at"])
        batches.add(item.batch_id)
    for b in PaymentBatch.objects.filter(pk__in=batches):
        if not b.items.filter(status=ItemStatus.ENVIADO).exists():
            b.status = BatchStatus.PROCESSADO
            b.save(update_fields=["status", "updated_at"])
            _maybe_mark_run_paid(b)
    f.summary = {**done, "nao_localizados": unknown}
    f.save(update_fields=["summary"])
    log_event("CREATE", module="financeiro.arquivos_bancarios", obj=f, object_repr=f"Retorno {f.file_name}",
              extra=f.summary)
    return f.summary


def _maybe_mark_run_paid(batch: PaymentBatch):
    """Folha passa a PAGA quando todos os líquidos positivos foram pagos pelo banco."""
    from apps.folha import services as folha_services
    from apps.folha.models import RunStatus

    run = batch.payroll_run
    if run.status != RunStatus.FECHADA:
        return
    positives = run.entries.filter(net__gt=0).count()
    paid = PaymentItem.objects.filter(payroll_entry__run=run, status=ItemStatus.PAGO).count()
    if positives and paid >= positives:
        folha_services.mark_paid(run, batch.payment_date)


@transaction.atomic
def mark_items_paid_manually(batch: PaymentBatch, justification: str) -> PaymentBatch:
    """Banco sem arquivo de retorno: confirmação manual (exige justificativa; fica na auditoria)."""
    _justify(justification)
    if batch.status != BatchStatus.ARQUIVO_GERADO:
        raise BusinessRuleError("Só lotes com arquivo gerado aguardando retorno.")
    n = batch.items.filter(status=ItemStatus.ENVIADO).update(status=ItemStatus.PAGO, return_message="Confirmado manualmente")
    batch.status = BatchStatus.PROCESSADO
    batch.save(update_fields=["status", "updated_at"])
    log_event("UPDATE", module="financeiro.pagamentos", obj=batch, object_repr=f"{batch} — pagamento confirmado manualmente",
              justification=justification, extra={"itens": n})
    _maybe_mark_run_paid(batch)
    return batch


# ================================================================== ARRECADAÇÃO
def _plan_for_segment(institution, segment: str):
    from apps.institutions.models import SEGMENT_PLAN_KIND, BenefitPlan

    return BenefitPlan.objects.filter(institution=institution, kind=SEGMENT_PLAN_KIND[segment], active=True) \
        .order_by("code").first()


def due_date_for(institution, competence: date) -> date:
    from apps.institutions.services import get_parameter

    day = int(get_parameter(institution, "arrecadacao.vencimento_dia", competence, default=20))
    nxt = add_months(competence, 1)
    return nxt.replace(day=min(day, calendar.monthrange(nxt.year, nxt.month)[1]))


def _rate(institution, key: str, on: date, label: str) -> Decimal:
    from apps.institutions.services import get_parameter

    v = get_parameter(institution, key, on)
    if v in (None, ""):
        raise BusinessRuleError(f"Alíquota {label} vigente em {on:%m/%Y} não cadastrada (parâmetro '{key}').")
    return Decimal(str(v))


@transaction.atomic
def estimate_contributions(institution, competence: date) -> dict:
    """
    Contribuições do servidor e patronal por órgão e plano, ESTIMADAS pelo vencimento base dos vínculos ativos.
    A base real (remuneração de contribuição) deve ser informada pelo órgão — edite a contribuição para corrigir.
    Contribuições já existentes da competência não são recriadas.
    """
    from apps.employment.models import ACTIVE_STATUSES, EmploymentLink

    competence = month_start(competence)
    r_serv = _rate(institution, "folha.aliquota_segurado", competence, "do servidor")
    r_pat = _rate(institution, "arrecadacao.aliquota_patronal", competence, "patronal")
    bases: dict = defaultdict(lambda: ZERO)
    missing = 0
    for lk in EmploymentLink.objects.filter(institution=institution, status__in=ACTIVE_STATUSES).select_related("organ"):
        if not lk.base_salary:
            missing += 1
            continue
        bases[(lk.organ_id, lk.segment)] += lk.base_salary
    created = 0
    due = due_date_for(institution, competence)
    for (organ_id, segment), base in bases.items():
        plan = _plan_for_segment(institution, segment)
        if plan is None:
            continue
        for kind, rate in ((ContributionKind.SERVIDOR, r_serv), (ContributionKind.PATRONAL, r_pat)):
            exists = Contribution.objects.filter(institution=institution, organ_id=organ_id, plan=plan, kind=kind,
                                                 competence=competence, active=True).exists()
            if exists:
                continue
            Contribution.objects.create(institution=institution, organ_id=organ_id, plan=plan, kind=kind,
                                        competence=competence, base=q(base), rate=rate, amount=q(base * rate),
                                        due_date=due, source="ESTIMADA")
            created += 1
    return {"criadas": created, "vinculos_sem_vencimento": missing}


@transaction.atomic
def contributions_from_payroll(run) -> Contribution:
    """Contribuição retida dos aposentados e pensionistas na folha FECHADA/PAGA (receita própria do plano)."""
    from apps.folha.models import PayrollItem, RunStatus

    if run.status not in (RunStatus.FECHADA, RunStatus.PAGA):
        raise BusinessRuleError("Use folha FECHADA ou PAGA.")
    if Contribution.objects.filter(payroll_run=run, active=True).exists():
        raise BusinessRuleError("As retenções desta folha já foram registradas.")
    items = PayrollItem.objects.filter(entry__run=run, rubric__calc__in=["CONTRIB_RPPS", "CONTRIB_13"])
    total = items.aggregate(s=Sum("amount"))["s"] or ZERO
    base = run.entries.aggregate(s=Sum("rpps_base"))["s"] or ZERO
    if total <= 0:
        raise BusinessRuleError("A folha não tem contribuição retida.")
    comp = date(run.competence.year, run.competence.month, 1)
    pay = run.payment_date or due_date_for(run.institution, comp)
    c = Contribution.objects.create(
        institution=run.institution, plan=run.payroll_group.plan, kind=ContributionKind.APOSENTADOS, competence=comp,
        base=base, rate=Decimal(0), amount=total, due_date=pay, source="FOLHA", payroll_run=run,
        notes=f"{run} — retenção em folha")
    Revenue.objects.create(institution=run.institution, plan=c.plan, kind=RevenueKind.CONTRIBUICAO, date=pay,
                           competence=comp, amount=total, contribution=c,
                           description=f"Contribuição retida na folha de benefícios {run.payroll_group.code}",
                           document=f"Folha {run.competence}")
    return c


def regenerate_installments(agreement: InstallmentAgreement):
    """Cronograma nominal (valor consolidado / nº de parcelas; a atualização é cobrada no pagamento)."""
    if agreement.parcels.filter(payments__isnull=False).exists():
        raise BusinessRuleError("Já há parcelas pagas: o cronograma não pode ser refeito.")
    agreement.parcels.all().delete()
    base = q(agreement.principal / agreement.installments)
    last = agreement.principal - base * (agreement.installments - 1)
    for n in range(1, agreement.installments + 1):
        Installment.objects.create(institution=agreement.institution, agreement=agreement, number=n,
                                   due_date=add_months(agreement.first_due, n - 1),
                                   amount=last if n == agreement.installments else base)


def paid_of(obj) -> Decimal:
    return obj.payments.filter(active=True).aggregate(s=Sum("amount"))["s"] or ZERO


def status_of(amount: Decimal, paid: Decimal, due: date, today: date | None = None) -> str:
    today = today or timezone.localdate()
    if paid >= amount:
        return "PAGO"
    if paid > 0:
        return "PARCIAL"
    return "VENCIDO" if due < today else "A_VENCER"


def reconciliation(institution, competence: date, plan_id=None) -> list[dict]:
    """Devido × pago por órgão, plano e tipo na competência."""
    competence = month_start(competence)
    rows = []
    qs = Contribution.objects.filter(institution=institution, competence=competence, active=True) \
        .select_related("organ", "plan")
    if plan_id:
        qs = qs.filter(plan_id=plan_id)
    for c in qs.order_by("plan__code", "organ__name", "kind"):
        paid = paid_of(c)
        last = c.payments.filter(active=True).order_by("-date").first()
        late = (last.date - c.due_date).days if last and last.date > c.due_date else 0
        rows.append({"id": str(c.pk), "plano": c.plan.code, "orgao": c.organ.name if c.organ else "Folha de benefícios",
                     "tipo": c.get_kind_display(), "kind": c.kind, "base": str(c.base), "aliquota": str(c.rate),
                     "devido": str(c.amount), "pago": str(paid), "diferenca": str(c.amount - paid),
                     "vencimento": c.due_date, "ultimo_pagamento": last.date if last else None,
                     "dias_atraso": late, "situacao": status_of(c.amount, paid, c.due_date), "origem": c.source})
    return rows


def divergences(institution, until: date | None = None) -> list[dict]:
    """Contribuições, aportes e parcelas vencidos e não pagos (ou pagos a menor ou com atraso)."""
    today = until or timezone.localdate()
    out = []
    for c in Contribution.objects.filter(institution=institution, active=True, due_date__lt=today) \
            .select_related("organ", "plan"):
        paid = paid_of(c)
        last = c.payments.filter(active=True).order_by("-date").first()
        late = last is not None and last.date > c.due_date
        if paid < c.amount or late:
            out.append({"tipo": c.get_kind_display(), "origem": "contribuicao", "id": str(c.pk), "plano": c.plan.code,
                        "devedor": c.organ.name if c.organ else "Folha de benefícios",
                        "competencia": f"{c.competence:%m/%Y}", "vencimento": c.due_date, "devido": str(c.amount),
                        "pago": str(paid), "diferenca": str(c.amount - paid),
                        "problema": "Pago com atraso" if paid >= c.amount else ("Pago a menor" if paid else "Não pago"),
                        "dias": ((last.date if late and paid >= c.amount else today) - c.due_date).days})
    for a in Aporte.objects.filter(institution=institution, active=True, due_date__lt=today).select_related("plan"):
        paid = paid_of(a)
        if paid < a.amount:
            out.append({"tipo": a.get_kind_display(), "origem": "aporte", "id": str(a.pk), "plano": a.plan.code,
                        "devedor": "Ente", "competencia": f"{a.competence:%m/%Y}", "vencimento": a.due_date,
                        "devido": str(a.amount), "pago": str(paid), "diferenca": str(a.amount - paid),
                        "problema": "Pago a menor" if paid else "Não pago", "dias": (today - a.due_date).days})
    for p in Installment.objects.filter(institution=institution, due_date__lt=today,
                                        agreement__status="ATIVO").select_related("agreement__organ", "agreement__plan"):
        paid = paid_of(p)
        if paid < p.amount:
            out.append({"tipo": f"Parcela {p.number}/{p.agreement.installments} — termo {p.agreement.number}",
                        "origem": "parcela", "id": str(p.pk), "plano": p.agreement.plan.code,
                        "devedor": p.agreement.organ.name, "competencia": f"{p.due_date:%m/%Y}", "vencimento": p.due_date,
                        "devido": str(p.amount), "pago": str(paid), "diferenca": str(p.amount - paid),
                        "problema": "Pago a menor" if paid else "Não pago", "dias": (today - p.due_date).days})
    out.sort(key=lambda r: (r["vencimento"], r["devedor"]))
    return out


def insufficiency(institution, competence: date) -> dict:
    """Insuficiência financeira do Plano Financeiro: despesa da folha − receitas do plano na competência."""
    from apps.folha.models import PayrollRun, RunStatus
    from apps.institutions.models import Segment

    competence = month_start(competence)
    plan = _plan_for_segment(institution, Segment.FINANCEIRO)
    if plan is None:
        raise BusinessRuleError("Plano Financeiro não cadastrado.")
    runs = PayrollRun.objects.filter(institution=institution, payroll_group__plan=plan,
                                     competence__year=competence.year, competence__month=competence.month,
                                     status__in=[RunStatus.FECHADA, RunStatus.PAGA])
    despesa = sum((Decimal(r.totals.get("proventos", "0")) for r in runs), ZERO)
    receitas = Revenue.objects.filter(institution=institution, plan=plan, competence=competence, active=True) \
        .exclude(kind=RevenueKind.APORTE).aggregate(s=Sum("amount"))["s"] or ZERO
    return {"plano": plan.code, "competencia": f"{competence:%m/%Y}", "despesa_folha": str(despesa),
            "receitas": str(receitas), "insuficiencia": str(max(ZERO, despesa - receitas)),
            "folhas_consideradas": len(runs)}


# ================================================================== CONCILIAÇÃO BANCÁRIA
@transaction.atomic
def import_statement(institution, account: TreasuryAccount, content: str, file_name: str) -> dict:
    data = ofx.parse(content)
    f = BankFile.objects.create(institution=institution, account=account, kind="EXTRATO", file_name=file_name[:120],
                                content=content, sha256=sha(content))
    new = dup = 0
    for ln in data["lines"]:
        if StatementLine.objects.filter(account=account, fitid=ln["fitid"]).exists():
            dup += 1
            continue
        StatementLine.objects.create(institution=institution, account=account, file=f, **ln)
        new += 1
    matched = auto_match(account)
    f.summary = {"lancamentos": new, "repetidos": dup, "conciliados_automaticamente": matched,
                 "conta_no_arquivo": data["account"]}
    f.save(update_fields=["summary"])
    return f.summary


def auto_match(account: TreasuryAccount, tolerance_days: int = 3) -> int:
    """Créditos = receitas da conta (mesmo valor, data ±3 dias). Débitos = total de lote pago (mesma data ±3)."""
    n = 0
    used_rev = set(StatementLine.objects.filter(account=account, revenue__isnull=False).values_list("revenue_id", flat=True))
    used_bat = set(StatementLine.objects.filter(account=account, batch__isnull=False).values_list("batch_id", flat=True))
    for ln in StatementLine.objects.filter(account=account, reconciled=False):
        win = (ln.date - timedelta(days=tolerance_days), ln.date + timedelta(days=tolerance_days))
        if ln.amount > 0:
            rev = (Revenue.objects.filter(institution=account.institution, active=True, date__range=win)
                   .filter(Q(account=account) | Q(account__isnull=True, plan=account.plan))
                   .exclude(pk__in=used_rev).filter(amount=ln.amount).first())
            if rev:
                ln.revenue, ln.reconciled = rev, True
                used_rev.add(rev.pk)
        else:
            bat = (PaymentBatch.objects.filter(account=account, payment_date__range=win, total=-ln.amount)
                   .exclude(status=BatchStatus.CANCELADO).exclude(pk__in=used_bat).first())
            if bat:
                ln.batch, ln.reconciled = bat, True
                used_bat.add(bat.pk)
        if ln.reconciled:
            ln.save(update_fields=["revenue", "batch", "reconciled", "updated_at"])
            n += 1
    return n


@transaction.atomic
def reconcile_manually(line: StatementLine, *, revenue=None, batch=None, note: str = "") -> StatementLine:
    if line.reconciled:
        raise BusinessRuleError("Lançamento já conciliado.")
    if revenue is None and batch is None:
        _justify(note)
    line.revenue, line.batch, line.note, line.reconciled = revenue, batch, note.strip()[:255], True
    line.save(update_fields=["revenue", "batch", "note", "reconciled", "updated_at"])
    log_event("UPDATE", module="financeiro.conciliacao", obj=line, object_repr=f"Conciliação manual {line.fitid}",
              justification=note or None)
    return line


# ================================================================== CONTABILIDADE
def accounting_lines(institution, plan, competence: date) -> tuple[list[dict], list[str]]:
    """Lançamentos da competência: rubricas das folhas fechadas do plano e receitas realizadas."""
    from apps.folha.models import PayrollItem, RunStatus

    competence = month_start(competence)
    maps = {(m.source, m.source_code): m for m in AccountingMapping.objects.filter(plan=plan, active=True)}
    out, unmapped = [], set()
    items = (PayrollItem.objects.filter(entry__run__payroll_group__plan=plan,
                                        entry__run__competence__year=competence.year,
                                        entry__run__competence__month=competence.month,
                                        entry__run__status__in=[RunStatus.FECHADA, RunStatus.PAGA])
             .values("code", "name", "entry__run__kind").annotate(total=Sum("amount")).order_by("code"))
    last_day = add_months(competence, 1) - timedelta(days=1)
    for it in items:
        m = maps.get(("RUBRICA", it["code"]))
        if m is None:
            unmapped.add(f"Rubrica {it['code']} — {it['name']}")
            continue
        out.append({"data": last_day, "debito": m.debit, "credito": m.credit, "valor": it["total"],
                    "historico": (m.history or f"Folha {competence:%m/%Y} — {it['name']}")[:150], "origem": f"rubrica {it['code']}"})
    for kind, total in (Revenue.objects.filter(institution=institution, plan=plan, competence=competence, active=True)
                        .values_list("kind").annotate(t=Sum("amount"))):
        m = maps.get(("RECEITA", kind))
        if m is None:
            unmapped.add(f"Receita {RevenueKind(kind).label}")
            continue
        out.append({"data": last_day, "debito": m.debit, "credito": m.credit, "valor": total,
                    "historico": (m.history or f"{RevenueKind(kind).label} {competence:%m/%Y}")[:150],
                    "origem": f"receita {kind}"})
    return out, sorted(unmapped)


@transaction.atomic
def export_accounting(institution, plan, competence: date) -> AccountingExport:
    lines, unmapped = accounting_lines(institution, plan, competence)
    if not lines:
        raise BusinessRuleError("Nenhum lançamento com de-para para exportar nesta competência.")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["data", "conta_debito", "conta_credito", "valor", "historico", "plano", "origem"])
    total = ZERO
    for ln in lines:
        w.writerow([ln["data"].strftime("%d/%m/%Y"), ln["debito"], ln["credito"], f"{ln['valor']:.2f}".replace(".", ","),
                    ln["historico"], plan.code, ln["origem"]])
        total += ln["valor"]
    content = buf.getvalue()
    exp = AccountingExport.objects.create(institution=institution, plan=plan, period=month_start(competence),
                                          lines=len(lines), total=total, content=content, sha256=sha(content),
                                          unmapped=unmapped)
    log_event("EXPORT", module="financeiro.integracao_contabil", obj=exp,
              object_repr=f"Exportação contábil {plan.code} {competence:%m/%Y}", extra={"sha256": exp.sha256})
    return exp


@transaction.atomic
def register_payment(target, *, amount, when: date, fines=ZERO, account: TreasuryAccount | None = None,
                     document: str = "", description: str = "") -> Revenue:
    """Baixa de contribuição, aporte ou parcela = receita realizada no MESMO plano (segregação)."""
    amount, fines = q(amount), q(fines or 0)
    if amount <= 0:
        raise BusinessRuleError("Informe o valor pago.")
    if isinstance(target, Contribution):
        plan, kind, comp, extra = target.plan, RevenueKind.CONTRIBUICAO, target.competence, {"contribution": target}
        desc = f"{target.get_kind_display()} — {target.organ.name if target.organ else 'folha'} {target.competence:%m/%Y}"
    elif isinstance(target, Aporte):
        plan, kind, comp, extra = target.plan, RevenueKind.APORTE, target.competence, {"aporte": target}
        desc = f"{target.get_kind_display()} {target.competence:%m/%Y}"
    elif isinstance(target, Installment):
        plan, kind, comp, extra = target.agreement.plan, RevenueKind.PARCELAMENTO, month_start(target.due_date), \
            {"installment": target}
        desc = f"Parcela {target.number}/{target.agreement.installments} — termo {target.agreement.number}"
    else:
        raise BusinessRuleError("Tipo de baixa inválido.")
    if account is not None and account.plan_id != plan.pk:
        raise BusinessRuleError(f"Segregação de massas: receita do plano {plan.code} não pode ser creditada na conta "
                                f"do plano {account.plan.code}.")
    rev = Revenue.objects.create(institution=plan.institution, plan=plan, kind=kind, date=when, competence=comp,
                                 amount=amount, fines=fines, account=account, document=document[:60],
                                 description=(description or desc)[:200], **extra)
    log_event("CREATE", module="arrecadacao.receitas", obj=rev, object_repr=f"Receita — {rev.description}",
              extra={"valor": str(amount), "encargos": str(fines)})
    return rev


@transaction.atomic
def reverse_revenue(rev: Revenue, justification: str) -> Revenue:
    _justify(justification)
    if not rev.active:
        raise BusinessRuleError("Receita já estornada.")
    if StatementLine.objects.filter(revenue=rev).exists():
        raise BusinessRuleError("Receita conciliada com o extrato: desfaça a conciliação antes.")
    rev.active = False
    rev.save(update_fields=["active", "updated_at"])
    log_event("UPDATE", module="arrecadacao.receitas", obj=rev, object_repr=f"Estorno — {rev.description}",
              justification=justification)
    return rev
