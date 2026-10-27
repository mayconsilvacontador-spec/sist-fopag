"""Ciclo da folha (abrir, calcular, conferir, fechar, reabrir, pagar), rubricas versionadas e relatórios."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from . import engine
from .models import (
    AUTOMATIC_CALCS, ENTRY_CALCS, Entry, PayrollEntry, PayrollItem, PayrollRun, Rubric, RubricKind, RunKind,
    RunStatus,
)
from .tax import ZERO, q

EDITABLE = {RunStatus.ABERTA, RunStatus.CALCULADA, RunStatus.CONFERIDA}


def _justify(text: str):
    if not text or len(text.strip()) < 10:
        raise BusinessRuleError("Informe uma justificativa com pelo menos 10 caracteres.")


def _log(run: PayrollRun, what: str, module: str, **kw):
    log_event("UPDATE", module=module, obj=run, object_repr=f"{run} — {what}", **kw)


# ------------------------------------------------------------------ rubricas
@transaction.atomic
def new_rubric_version(rubric: Rubric, data: dict, valid_from: date, reason: str) -> Rubric:
    """Nova versão da rubrica: a anterior é encerrada no dia anterior. Folhas antigas guardam a versão usada."""
    _justify(reason)
    last = Rubric.objects.select_for_update().filter(institution=rubric.institution, code=rubric.code) \
        .order_by("-version").first()
    if valid_from <= last.valid_from:
        raise BusinessRuleError("A nova versão deve começar depois do início da versão vigente.")
    last.valid_to = valid_from - timedelta(days=1)
    last.save(update_fields=["valid_to", "updated_at", "updated_by"])
    fields = {f: getattr(last, f) for f in ("name", "kind", "calc", "inc_ir", "inc_rpps", "inc_13", "inc_margem",
                                            "ir_deduction", "esocial_nature", "esocial_inc_cp", "esocial_inc_irrf",
                                            "esocial_inc_cprp")}
    fields.update({k: v for k, v in data.items() if k in fields})
    new = Rubric.objects.create(institution=rubric.institution, code=rubric.code, version=last.version + 1,
                                valid_from=valid_from, change_reason=reason.strip(), **fields)
    validate_rubric(new)
    return new


def validate_rubric(r: Rubric):
    if r.calc in AUTOMATIC_CALCS:
        clash = (Rubric.objects.filter(institution=r.institution, calc=r.calc, active=True)
                 .exclude(code=r.code).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=r.valid_from)))
        if clash.exists():
            raise BusinessRuleError(f"Já existe rubrica ativa com a forma de cálculo '{r.get_calc_display()}' "
                                    f"({clash.first().code}). Cada cálculo automático tem uma única rubrica.")
    expected = {"CONTRIB_RPPS": "DESCONTO", "CONTRIB_13": "DESCONTO", "IRRF": "DESCONTO", "IRRF_13": "DESCONTO",
                "IRRF_RRA": "DESCONTO", "PENSAO_ALIMENTICIA": "DESCONTO", "PENSAO_ALIMENTICIA_13": "DESCONTO",
                "CONSIGNACAO": "DESCONTO", "APOSENTADORIA": "PROVENTO", "PENSAO": "PROVENTO",
                "RETROATIVO": "PROVENTO", "DECIMO": "PROVENTO"}.get(r.calc)
    if expected and r.kind != expected:
        raise BusinessRuleError(f"A forma de cálculo '{r.get_calc_display()}' exige rubrica do tipo {expected.lower()}.")


# ------------------------------------------------------------------ lançamentos
def validate_entry(e: Entry):
    r = Rubric.objects.filter(institution=e.institution, code=e.rubric_code, active=True).order_by("-version").first()
    if r is None:
        raise BusinessRuleError(f"Rubrica {e.rubric_code} não encontrada.")
    if r.calc not in ENTRY_CALCS:
        raise BusinessRuleError(f"A rubrica {r.code} é calculada automaticamente e não aceita lançamentos.")
    if e.amount is None and e.percent is None:
        raise BusinessRuleError("Informe o valor ou o percentual.")
    if e.amount is not None and e.amount <= 0 or e.percent is not None and not (0 < e.percent <= 100):
        raise BusinessRuleError("Valor ou percentual inválido.")
    e.start = e.start.replace(day=1)
    if e.end:
        e.end = e.end.replace(day=1)
        if e.end < e.start:
            raise BusinessRuleError("A competência final não pode ser anterior à inicial.")
    if r.calc == "PENSAO_ALIMENTICIA":
        if not e.contract:
            raise BusinessRuleError("Informe o processo judicial / acordo da pensão alimentícia.")
        if e.percent is not None and not e.base:
            e.base = "BRUTO"
    if r.calc == "CONSIGNACAO" and not e.consignee_id:
        raise BusinessRuleError("Informe a consignatária.")
    return r


# ------------------------------------------------------------------ folhas
def get_or_create_competence(institution, year: int, month: int):
    from apps.institutions.models import Competence, FiscalYear, FiscalYearStatus

    if not (1 <= month <= 12 and 2000 <= year <= 2100):
        raise BusinessRuleError("Competência inválida.")
    fy, _ = FiscalYear.objects.get_or_create(institution=institution, year=year)
    if fy.status == FiscalYearStatus.FECHADO:
        raise BusinessRuleError(f"O exercício {year} está fechado.")
    comp, _ = Competence.objects.get_or_create(institution=institution, year=year, month=month,
                                               defaults={"fiscal_year": fy})
    return comp


@transaction.atomic
def open_run(institution, *, year: int, month: int, payroll_group, kind: str = RunKind.MENSAL) -> PayrollRun:
    if payroll_group.institution_id != institution.pk or not payroll_group.active:
        raise BusinessRuleError("Folha (massa) inválida ou inativa.")
    if kind == RunKind.DECIMO and month not in (11, 12):
        raise BusinessRuleError("A folha de 13º deve ser aberta em novembro ou dezembro.")
    comp = get_or_create_competence(institution, year, month)
    if PayrollRun.objects.filter(competence=comp, payroll_group=payroll_group, kind=kind).exists():
        raise BusinessRuleError(f"A folha {payroll_group.code} de {comp} ({RunKind(kind).label.lower()}) já existe.")
    if kind == RunKind.DECIMO and PayrollRun.objects.filter(
            payroll_group=payroll_group, kind=RunKind.DECIMO, competence__year=year).exists():
        raise BusinessRuleError(f"Já existe folha de 13º de {year} para {payroll_group.code}.")
    if kind == RunKind.MENSAL:
        pending = PayrollRun.objects.filter(payroll_group=payroll_group, kind=kind, status__in=EDITABLE).first()
        if pending:
            raise BusinessRuleError(f"Feche antes a folha {pending.competence} desta massa.")
        last = (PayrollRun.objects.filter(payroll_group=payroll_group, kind=kind)
                .order_by("-competence__year", "-competence__month").select_related("competence").first())
        if last:
            ny, nm = (last.competence.year + 1, 1) if last.competence.month == 12 else (last.competence.year,
                                                                                         last.competence.month + 1)
            if (year, month) != (ny, nm):
                raise BusinessRuleError(f"A próxima folha mensal de {payroll_group.code} é {nm:02d}/{ny} "
                                        f"(última: {last.competence}). Não é possível pular competências.")
    run = PayrollRun.objects.create(institution=institution, competence=comp, payroll_group=payroll_group, kind=kind)
    log_event("CREATE", module="folha.folha_mensal", obj=run, object_repr=str(run))
    return run


def _bank_snapshot(person, on: date) -> dict:
    from apps.people.models import BankAccount

    acc = (BankAccount.objects.filter(person=person, valid_from__lte=on).filter(Q(valid_to__isnull=True) |
                                                                                  Q(valid_to__gte=on))
           .select_related("bank").order_by("-valid_from").first())
    if acc is None:
        return {}
    return {"banco": acc.bank.code, "banco_nome": acc.bank.name, "agencia": acc.branch,
            "agencia_dv": acc.branch_digit, "conta": acc.account, "conta_dv": acc.account_digit,
            "tipo": acc.account_type}


@transaction.atomic
def calculate(run: PayrollRun) -> PayrollRun:
    run = PayrollRun.objects.select_for_update().get(pk=run.pk)
    if run.status not in EDITABLE:
        raise BusinessRuleError(f"Folha {run.get_status_display().lower()} não pode ser recalculada. "
                                "Para corrigir, reabra a folha (com justificativa).")
    ctx = engine.Context(run)
    slips = engine.calculate_decimo(ctx) if run.kind == RunKind.DECIMO else engine.calculate_monthly(ctx)
    run.entries.all().delete()
    totals = {"beneficiarios": 0, "proventos": ZERO, "descontos": ZERO, "liquido": ZERO, "sem_conta": 0,
              "liquido_negativo": 0, "aposentados": 0, "pensionistas": 0}
    for s in slips:
        b = s.benefit
        gross, disc = s.total(RubricKind.PROVENTO), s.total(RubricKind.DESCONTO)
        bank = _bank_snapshot(b.beneficiary, ctx.m1)
        if not bank:
            s.warnings.append("Beneficiário sem conta bancária vigente — crédito não será gerado.")
            totals["sem_conta"] += 1
        if gross - disc < 0:
            s.warnings.append("Líquido negativo — revise os descontos.")
            totals["liquido_negativo"] += 1
        pe = PayrollEntry.objects.create(
            institution=run.institution, run=run, benefit=b, beneficiary=b.beneficiary, gross=gross, discounts=disc,
            net=gross - disc, ir_base=Decimal(s.memory.get("irrf" if run.kind == RunKind.MENSAL else "irrf_13", {})
                                              .get("base", "0")),
            rpps_base=s.rpps_base, bank=bank, memory=s.memory, warnings=s.warnings)
        PayrollItem.objects.bulk_create([
            PayrollItem(institution=run.institution, entry=pe, rubric=ln.rubric, code=ln.rubric.code,
                        name=ln.name[:120], kind=ln.rubric.kind, reference=ln.reference[:30], amount=ln.amount,
                        source_entry=ln.source_entry)
            for ln in s.lines])
        totals["beneficiarios"] += 1
        totals["aposentados" if b.kind == "APOSENTADORIA" else "pensionistas"] += 1
        totals["proventos"] += gross
        totals["descontos"] += disc
        totals["liquido"] += gross - disc
    run.totals = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in totals.items()}
    run.warnings = ctx.warnings
    run.status = RunStatus.CALCULADA
    run.calculated_at = timezone.now()
    run.checked_by, run.checked_at = None, None
    run.save()
    _log(run, "cálculo", "folha.calculo", extra={"beneficiarios": totals["beneficiarios"],
                                                 "liquido": str(totals["liquido"])})
    return run


@transaction.atomic
def check(run: PayrollRun, user) -> PayrollRun:
    if run.status != RunStatus.CALCULADA:
        raise BusinessRuleError("Só é possível conferir uma folha calculada.")
    run.status, run.checked_by, run.checked_at = RunStatus.CONFERIDA, user, timezone.now()
    run.save(update_fields=["status", "checked_by", "checked_at", "updated_at"])
    _log(run, "conferência", "folha.conferencia")
    return run


@transaction.atomic
def close(run: PayrollRun, user) -> PayrollRun:
    run = PayrollRun.objects.select_for_update().get(pk=run.pk)
    if run.status != RunStatus.CONFERIDA:
        raise BusinessRuleError("A folha precisa estar conferida para ser fechada.")
    effects = []
    for item in PayrollItem.objects.filter(entry__run=run, source_entry__isnull=False).select_related("source_entry"):
        e = item.source_entry
        if not e.installments:
            continue
        e.paid_installments += 1
        finished = e.paid_installments >= e.installments
        if finished:
            e.active = False
        e.save(update_fields=["paid_installments", "active", "updated_at"])
        effects.append({"entry": str(e.pk), "finished": finished})
    run.status, run.closed_by, run.closed_at = RunStatus.FECHADA, user, timezone.now()
    run.close_effects = {"parcelas": effects}
    run.save(update_fields=["status", "closed_by", "closed_at", "close_effects", "updated_at"])
    log_event("CLOSE", module="folha.fechamento", obj=run, object_repr=str(run))
    return run


@transaction.atomic
def reopen(run: PayrollRun, justification: str) -> PayrollRun:
    run = PayrollRun.objects.select_for_update().get(pk=run.pk)
    if run.status != RunStatus.FECHADA:
        raise BusinessRuleError("Só folhas fechadas (ainda não pagas) podem ser reabertas.")
    _justify(justification)
    later = PayrollRun.objects.filter(payroll_group=run.payroll_group, kind=run.kind).filter(
        Q(competence__year__gt=run.competence.year) |
        Q(competence__year=run.competence.year, competence__month__gt=run.competence.month)).exclude(
        status=RunStatus.ABERTA).first()
    if later:
        raise BusinessRuleError(f"Existe folha posterior já calculada ({later.competence}). Reabra-a antes.")
    for eff in (run.close_effects or {}).get("parcelas", []):
        e = Entry.objects.filter(pk=eff["entry"]).first()
        if e:
            e.paid_installments = max(0, e.paid_installments - 1)
            if eff.get("finished"):
                e.active = True
            e.save(update_fields=["paid_installments", "active", "updated_at"])
    run.status, run.closed_by, run.closed_at, run.close_effects = RunStatus.CONFERIDA, None, None, {}
    run.save(update_fields=["status", "closed_by", "closed_at", "close_effects", "updated_at"])
    log_event("REOPEN", module="folha.reabertura", obj=run, object_repr=str(run), justification=justification)
    return run


@transaction.atomic
def mark_paid(run: PayrollRun, payment_date: date) -> PayrollRun:
    if run.status != RunStatus.FECHADA:
        raise BusinessRuleError("Só folhas fechadas podem ser marcadas como pagas.")
    run.status, run.payment_date = RunStatus.PAGA, payment_date
    run.save(update_fields=["status", "payment_date", "updated_at"])
    _log(run, f"pagamento em {payment_date:%d/%m/%Y}", "folha.fechamento")
    return run


@transaction.atomic
def delete_run(run: PayrollRun, user, justification: str, password: str) -> None:
    """
    Exclui uma folha aberta por engano. Só a ÚLTIMA folha da massa/tipo (não abre buraco na sequência), sem lote de
    pagamento, sem contribuição gerada e sem evento do eSocial. Folha paga só se não tiver beneficiário (nenhum
    dinheiro saiu). Fechada: desfaz as parcelas baixadas no fechamento. Fica registrada na auditoria com os totais.
    """
    from apps.concessao.workflow import confirm_password
    from apps.esocial.models import EsocialEvent
    from apps.financeiro.models import Contribution

    run = PayrollRun.objects.select_for_update().select_related("competence", "payroll_group").get(pk=run.pk)
    _justify(justification)
    confirm_password(user, password)
    beneficiarios = run.entries.count()
    if run.status == RunStatus.PAGA and beneficiarios:
        raise BusinessRuleError("Folha paga com beneficiários não pode ser excluída: o pagamento já foi feito.")
    later = PayrollRun.objects.filter(payroll_group=run.payroll_group, kind=run.kind).filter(
        Q(competence__year__gt=run.competence.year) |
        Q(competence__year=run.competence.year, competence__month__gt=run.competence.month)).first()
    if later:
        raise BusinessRuleError(f"Existe folha posterior desta massa ({later.competence}). Exclua as folhas a partir "
                                "da mais recente.")
    if run.payment_batches.exists():
        raise BusinessRuleError("A folha tem lote de pagamento no Financeiro. Cancele o lote antes.")
    if Contribution.objects.filter(payroll_run=run).exists():
        raise BusinessRuleError("A folha gerou contribuições na Arrecadação. Inative-as antes.")
    if EsocialEvent.objects.filter(object_id__startswith=f"{run.pk}:").exists():
        raise BusinessRuleError("A folha já gerou eventos do eSocial; não pode ser excluída.")
    for eff in (run.close_effects or {}).get("parcelas", []):
        e = Entry.objects.filter(pk=eff["entry"]).first()
        if e:
            e.paid_installments = max(0, e.paid_installments - 1)
            if eff.get("finished"):
                e.active = True
            e.save(update_fields=["paid_installments", "active", "updated_at"])
    log_event("DELETE", module="folha.folha_mensal", obj=run, object_repr=f"{run} — exclusão",
              justification=justification.strip(),
              extra={"situacao": run.status, "beneficiarios": beneficiarios, "totais": run.totals or {}})
    run.delete()


# ------------------------------------------------------------------ relatórios
def previous_run(run: PayrollRun) -> PayrollRun | None:
    c = run.competence
    return (PayrollRun.objects.filter(payroll_group=run.payroll_group, kind=RunKind.MENSAL)
            .filter(Q(competence__year__lt=c.year) | Q(competence__year=c.year, competence__month__lt=c.month))
            .exclude(status=RunStatus.ABERTA)
            .order_by("-competence__year", "-competence__month").first())


def comparison(run: PayrollRun, threshold: Decimal = Decimal("5")) -> dict:
    """Conferência: entradas, saídas e variações do líquido acima de threshold% em relação à folha anterior."""
    prev = previous_run(run) if run.kind == RunKind.MENSAL else None
    cur = {e.benefit_id: e for e in run.entries.select_related("beneficiary")}
    old = {e.benefit_id: e for e in prev.entries.select_related("beneficiary")} if prev else {}
    row = lambda e: {"id": str(e.pk), "beneficiario": e.beneficiary.name, "liquido": str(e.net)}  # noqa: E731
    entradas = [row(e) for k, e in cur.items() if k not in old]
    saidas = [row(e) for k, e in old.items() if k not in cur]
    variacoes = []
    for k, e in cur.items():
        if k in old and old[k].net:
            pct = (e.net - old[k].net) / old[k].net * 100
            if abs(pct) >= threshold:
                variacoes.append({**row(e), "anterior": str(old[k].net), "variacao_pct": str(q(pct))})
    variacoes.sort(key=lambda x: -abs(Decimal(x["variacao_pct"])))
    avisos = [{"id": str(e.pk), "beneficiario": e.beneficiary.name, "avisos": e.warnings}
              for e in cur.values() if e.warnings]
    return {"anterior": str(prev.competence) if prev else None,
            "totais_anterior": prev.totals if prev else None, "totais": run.totals,
            "entradas": entradas, "saidas": saidas, "variacoes": variacoes, "avisos": avisos}


def rubric_summary(run: PayrollRun) -> list[dict]:
    agg: dict = defaultdict(lambda: {"quantidade": 0, "valor": ZERO})
    for it in PayrollItem.objects.filter(entry__run=run).values("code", "name", "kind", "amount", "rubric__name"):
        key = (it["code"], it["rubric__name"], it["kind"])
        agg[key]["quantidade"] += 1
        agg[key]["valor"] += it["amount"]
    order = {"PROVENTO": 0, "DESCONTO": 1, "INFORMATIVA": 2}
    return [{"codigo": k[0], "rubrica": k[1], "tipo": k[2], "quantidade": v["quantidade"], "valor": str(v["valor"])}
            for k, v in sorted(agg.items(), key=lambda kv: (order[kv[0][2]], kv[0][0]))]


def credit_list(run: PayrollRun) -> list[dict]:
    rows = []
    for e in run.entries.select_related("beneficiary").order_by("beneficiary__name"):
        if e.net <= 0:
            continue
        b = e.bank or {}
        rows.append({"banco": b.get("banco", ""), "banco_nome": b.get("banco_nome", ""),
                     "agencia": f"{b.get('agencia', '')}{'-' + b['agencia_dv'] if b.get('agencia_dv') else ''}",
                     "conta": f"{b.get('conta', '')}{'-' + b['conta_dv'] if b.get('conta_dv') else ''}",
                     "tipo": b.get("tipo", ""), "cpf": e.beneficiary.cpf, "nome": e.beneficiary.name,
                     "liquido": str(e.net)})
    rows.sort(key=lambda r: (r["banco"] or "999", r["nome"]))
    return rows


def income_report(institution, person, year: int) -> dict:
    """Informe de rendimentos (folhas fechadas/pagas do ano, por competência)."""
    entries = (PayrollEntry.objects.filter(institution=institution, beneficiary=person, run__competence__year=year,
                                           run__status__in=[RunStatus.FECHADA, RunStatus.PAGA])
               .select_related("run").prefetch_related("items"))
    t = defaultdict(lambda: ZERO)
    for e in entries:
        m = e.memory or {}
        calcs = {it.code: it for it in e.items.all()}
        for it in calcs.values():
            calc = it.rubric.calc if it.rubric_id else ""
            if calc in ("CONTRIB_RPPS",):
                t["contribuicao"] += it.amount
            elif calc == "CONTRIB_13":
                t["contribuicao_13"] += it.amount
            elif calc == "IRRF":
                t["irrf"] += it.amount
            elif calc == "IRRF_13":
                t["irrf_13"] += it.amount
            elif calc == "IRRF_RRA":
                t["irrf_rra"] += it.amount
            elif calc == "PENSAO_ALIMENTICIA":
                t["pensao_alimenticia"] += it.amount
            elif calc == "PENSAO_ALIMENTICIA_13":
                t["pensao_alimenticia_13"] += it.amount
        if e.run.kind == RunKind.DECIMO:
            t["decimo"] += Decimal(m.get("decimo_tributavel", "0"))
            t["decimo_isento"] += Decimal(m.get("decimo_isento_65", "0")) + Decimal(m.get("decimo_isento_molestia", "0"))
            t["isento_65"] += Decimal(m.get("decimo_isento_65", "0"))
            t["isento_molestia"] += Decimal(m.get("decimo_isento_molestia", "0"))
        else:
            trib = Decimal(m.get("tributavel", "0"))
            isento = Decimal(m.get("isento_65", "0"))
            molestia = Decimal(m.get("isento_molestia", "0"))
            t["isento_65"] += isento
            t["isento_molestia"] += molestia
            t["tributavel"] += trib - isento - molestia
            if m.get("rra"):
                t["rra_rendimento"] += Decimal(m["rra"]["rendimento"])
                t["rra_contribuicao"] += Decimal(m["rra"]["contribuicao"])
                t["rra_meses"] += m["rra"]["meses"]
    # 13º no informe: valor líquido das deduções (contribuição, dependentes e pensão alimentícia)
    decimo_entry = next((e for e in entries if e.run.kind == RunKind.DECIMO), None)
    if decimo_entry is not None:
        from .tax import IrTable

        deps = (decimo_entry.memory.get("irrf_13") or {}).get("dependentes", 0)
        dep_value = IrTable.load(institution, date(year, 12, 1)).dependent * deps
        t["decimo"] = max(ZERO, t["decimo"] - t["decimo_isento"] - t["contribuicao_13"] - t["pensao_alimenticia_13"]
                          - dep_value)
    return {"ano_calendario": year, "beneficiario": person.name, "cpf": person.cpf,
            "fonte_pagadora": {"nome": institution.name, "cnpj": institution.cnpj or ""},
            "quadro_3": {"1_rendimentos_tributaveis": str(t["tributavel"]),
                         "2_contribuicao_previdenciaria_oficial": str(t["contribuicao"]),
                         "4_pensao_alimenticia": str(t["pensao_alimenticia"]),
                         "5_irrf": str(t["irrf"])},
            "quadro_4": {"1_parcela_isenta_65_anos": str(t["isento_65"]),
                         "3_molestia_grave": str(t["isento_molestia"])},
            "quadro_5": {"1_decimo_terceiro": str(t["decimo"]), "2_irrf_decimo_terceiro": str(t["irrf_13"]),
                         "contribuicao_13": str(t["contribuicao_13"]),
                         "pensao_alimenticia_13": str(t["pensao_alimenticia_13"])},
            "rra": {"rendimento": str(t["rra_rendimento"]), "contribuicao": str(t["rra_contribuicao"]),
                    "irrf": str(t["irrf_rra"]), "meses": int(t["rra_meses"])} if t["rra_rendimento"] else None,
            "competencias": sorted({str(e.run.competence) for e in entries})}
