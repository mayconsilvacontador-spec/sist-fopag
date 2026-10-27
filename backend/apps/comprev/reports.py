"""Relatórios do COMPREV (telas COMPREV › Relatórios e Relatórios › COMPREV)."""
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.validators import format_cpf
from apps.reports.registry import col, report, result

from . import services
from .models import ComprevProcess, Direction, Movement, Status

ZERO = Decimal("0.00")
ALSO = ("relatorios.comprev",)
SENTIDO = {"key": "sentido", "label": "Sentido", "type": "select", "default": "",
           "options": [["", "Todos"], ["RECEBER", "A receber"], ["PAGAR", "A pagar"]]}
SITUACAO = {"key": "situacao", "label": "Situação", "type": "select", "default": "",
            "options": [["", "Todas"]] + [[s.value, s.label] for s in Status]}


def _comp(p, key="competencia"):
    v = p.get(key) or ""
    try:
        y, m = v.split("-")[:2]
        return date(int(y), int(m), 1)
    except ValueError:
        today = timezone.localdate()
        return date(today.year, today.month, 1)


def _year(p):
    try:
        return int(p.get("ano") or timezone.localdate().year)
    except ValueError:
        raise BusinessRuleError("Ano inválido.")


@report("comprev-requerimentos", "comprev.relatorios", "Requerimentos COMPREV",
        "Requerimentos a receber e a pagar, com situação, valor mensal vigente e atrasados.", [SENTIDO, SITUACAO],
        landscape=True, also=ALSO)
def requerimentos(inst, p):
    qs = ComprevProcess.objects.filter(institution=inst).select_related("person", "plan").order_by("direction", "person__name")
    if p.get("sentido"):
        qs = qs.filter(direction=p["sentido"])
    if p.get("situacao"):
        qs = qs.filter(status=p["situacao"])
    rows = [{"sentido": x.get_direction_display().split(" (")[0], "nome": x.person.name, "cpf": format_cpf(x.person.cpf),
             "beneficio": x.get_benefit_kind_display(), "regime": x.counterpart_name, "numero": x.request_number,
             "requerido": x.requested_at, "situacao": x.get_status_display(), "plano": x.plan.code,
             "valor": services.current_value(x) if x.status == Status.DEFERIDO else None,
             "atrasados": x.backlog_amount or None} for x in qs]
    total = sum((r["valor"] or ZERO for r in rows), ZERO)
    return result([col("sentido", "Sentido"), col("nome", "Segurado / instituidor"), col("cpf", "CPF"),
                   col("beneficio", "Benefício"), col("regime", "Outro regime"), col("numero", "Nº COMPREV"),
                   col("requerido", "Requerido em", "date"), col("situacao", "Situação"), col("plano", "Plano"),
                   col("valor", "Valor mensal", "money"), col("atrasados", "Atrasados", "money")],
                  rows, {"nome": f"{len(rows)} requerimento(s)", "valor": total})


@report("comprev-fluxo", "comprev.relatorios", "Fluxo mensal — previsto × realizado",
        "Na competência: valor previsto de cada requerimento deferido, o que foi recebido/pago e a diferença.",
        [{"key": "competencia", "label": "Competência", "type": "competencia", "default": "mes_anterior"}, SENTIDO], landscape=True, also=ALSO)
def fluxo(inst, p):
    f = services.flow(inst, _comp(p), p.get("sentido") or None)
    rows = [{"sentido": "A receber" if r["direction"] == Direction.RECEBER else "A pagar", "nome": r["person"],
             "regime": r["counterpart"], "numero": r["request_number"], "plano": r["plan"], "previsto": r["expected"],
             "realizado": r["realized"], "diferenca": r["difference"],
             "situacao": "Registrado" if r["registered"] else ("Não registrado" if r["expected"] else "Acerto")}
            for r in f["linhas"]]
    rec, pag = f["totais"][Direction.RECEBER], f["totais"][Direction.PAGAR]
    return result([col("sentido", "Sentido"), col("nome", "Segurado / instituidor"), col("regime", "Outro regime"),
                   col("numero", "Nº COMPREV"), col("plano", "Plano"), col("previsto", "Previsto", "money"),
                   col("realizado", "Realizado", "money"), col("diferenca", "Diferença", "money"),
                   col("situacao", "Situação")], rows,
                  {"nome": f"{f['competencia']:%m/%Y}", "previsto": sum((r["previsto"] for r in rows), ZERO),
                   "realizado": sum((r["realizado"] for r in rows), ZERO),
                   "diferenca": sum((r["diferenca"] for r in rows), ZERO)},
                  [f"A receber: previsto {rec['previsto']} · recebido {rec['realizado']}",
                   f"A pagar: previsto {pag['previsto']} · pago {pag['realizado']}",
                   f"Saldo do mês (recebido − pago): {f['saldo']}"])


@report("comprev-movimentos", "comprev.relatorios", "Recebimentos e pagamentos do ano",
        "Todos os valores lançados no ano (fluxo mensal, atrasados, ajustes e glosas), com a receita no Financeiro.",
        [{"key": "ano", "label": "Ano", "type": "ano", "default": "atual"}, SENTIDO], landscape=True, also=ALSO)
def movimentos(inst, p):
    year = _year(p)
    qs = (Movement.objects.filter(institution=inst, active=True, competence__year=year)
          .select_related("process__person", "plan").order_by("competence", "process__person__name"))
    if p.get("sentido"):
        qs = qs.filter(direction=p["sentido"])
    rows = [{"competencia": m.competence.strftime("%m/%Y"), "sentido": "Recebido" if m.direction == Direction.RECEBER
             else "Pago", "nome": m.process.person.name, "tipo": m.get_kind_display(), "plano": m.plan.code,
             "data": m.date, "documento": m.document, "valor": m.signed, "receita": bool(m.revenue_id)} for m in qs]
    rec = sum((r["valor"] for r in rows if r["sentido"] == "Recebido"), ZERO)
    pag = sum((r["valor"] for r in rows if r["sentido"] == "Pago"), ZERO)
    return result([col("competencia", "Competência"), col("sentido", "Sentido"), col("nome", "Segurado / instituidor"),
                   col("tipo", "Tipo"), col("plano", "Plano"), col("data", "Data", "date"), col("documento", "Documento"),
                   col("valor", "Valor", "money"), col("receita", "No Financeiro", "bool")], rows,
                  {"competencia": f"{len(rows)} lançamento(s)"},
                  [f"Total recebido em {year}: {rec}", f"Total pago em {year}: {pag}", f"Saldo: {rec - pag}"])


@report("comprev-potencial", "comprev.relatorios", "Benefícios sem requerimento COMPREV",
        "Aposentadorias e pensões ativas cujo segurado (ou instituidor) tem tempo averbado de outro regime marcado "
        "como sujeito ao COMPREV e ainda não tem requerimento a receber.", [], also=ALSO)
def potencial(inst, p):
    rows = [{"nome": owner.name, "cpf": format_cpf(owner.cpf), "beneficio": b.get_kind_display(),
             "inicio": b.start_date, "valor": b.amount, "plano": b.payroll_group.plan.code}
            for b, owner in services.potential(inst)]
    return result([col("nome", "Segurado / instituidor"), col("cpf", "CPF"), col("beneficio", "Benefício"),
                   col("inicio", "Início", "date"), col("valor", "Valor do benefício", "money"), col("plano", "Plano")],
                  rows, {"nome": f"{len(rows)} benefício(s) sem requerimento"})


@report("comprev-exigencias", "comprev.relatorios", "Exigências em aberto",
        "Requerimentos em exigência no COMPREV, com o prazo para cumprir.", [], also=ALSO)
def exigencias(inst, p):
    today = timezone.localdate()
    qs = (ComprevProcess.objects.filter(institution=inst, status=Status.EXIGENCIA).select_related("person")
          .order_by("requirement_due"))
    rows = [{"nome": x.person.name, "sentido": x.get_direction_display().split(" (")[0], "numero": x.request_number,
             "exigencia": x.requirement_text, "prazo": x.requirement_due,
             "dias": (x.requirement_due - today).days if x.requirement_due else None} for x in qs]
    return result([col("nome", "Segurado / instituidor"), col("sentido", "Sentido"), col("numero", "Nº COMPREV"),
                   col("exigencia", "Exigência"), col("prazo", "Prazo", "date"), col("dias", "Dias restantes", "int")],
                  rows, {"nome": f"{len(rows)} exigência(s)"})


