"""
Relatórios do SIST (telas Relatórios › Previdenciários, Benefícios, Folha, Financeiros, Gerenciais, Estatísticos e
eSocial). Só leitura: nenhum relatório altera dados. Valores em Decimal; datas no fuso de Brasília.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .registry import PLANO_FILTER, col, report, result

ZERO = Decimal("0")
SEX = {1: "F", 2: "M"}
YEAR = {"key": "ano", "label": "Ano", "type": "ano", "default": "atual"}
COMP = {"key": "competencia", "label": "Competência", "type": "competencia", "default": "ultima_folha"}
PERIOD = [{"key": "inicio", "label": "De", "type": "data", "default": "inicio_ano"},
          {"key": "fim", "label": "Até", "type": "data", "default": "hoje"}]


# ---------------------------------------------------------------- utilitários
def _today():
    return timezone.localdate()


def _age(birth, on=None):
    if not birth:
        return None
    on = on or _today()
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def _year(p) -> int:
    try:
        return int(p.get("ano") or _today().year)
    except ValueError:
        raise BusinessRuleError("Ano inválido.")


def _period(p) -> tuple[date, date]:
    try:
        start = date.fromisoformat(p["inicio"]) if p.get("inicio") else date(_today().year, 1, 1)
        end = date.fromisoformat(p["fim"]) if p.get("fim") else _today()
    except ValueError:
        raise BusinessRuleError("Período inválido.")
    if start > end:
        raise BusinessRuleError("A data inicial é posterior à final.")
    return start, end


def _competence(inst, p) -> tuple[int, int]:
    """AAAA-MM; padrão: competência da última folha calculada."""
    v = (p.get("competencia") or "").strip()
    if v:
        try:
            y, m = v.split("-")
            return int(y), int(m)
        except ValueError:
            raise BusinessRuleError("Competência inválida (use AAAA-MM).")
    from apps.folha.models import PayrollRun

    last = (PayrollRun.objects.filter(institution=inst).exclude(status="ABERTA")
            .order_by("-competence__year", "-competence__month").select_related("competence").first())
    if last is None:
        raise BusinessRuleError("Nenhuma folha calculada ainda — informe a competência.")
    return last.competence.year, last.competence.month


def _cpf(v: str) -> str:
    return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}" if v and len(v) == 11 else (v or "")


def _money(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return ZERO


# ================================================================= PREVIDENCIÁRIOS
@report("servidores-ativos", "relatorios.previdenciarios", "Servidores ativos (segurados do RPPS)",
        "Vínculos estatutários ativos, com órgão, cargo, ingresso e massa.", [PLANO_FILTER], landscape=True)
def servidores_ativos(inst, p):
    from apps.employment.models import EmploymentLink

    qs = (EmploymentLink.objects.filter(institution=inst, regime="ESTATUTARIO", status="ATIVO")
          .select_related("person", "organ", "position").order_by("person__name"))
    if p.get("plano"):
        qs = qs.filter(segment=p["plano"])
    rows = [{"matricula": lk.registration, "nome": lk.person.name, "cpf": _cpf(lk.person.cpf),
             "sexo": SEX.get(lk.person.sex, ""), "nascimento": lk.person.birth_date, "idade": _age(lk.person.birth_date),
             "orgao": lk.organ.short_name or lk.organ.name, "cargo": lk.position.name, "ingresso": lk.ente_start,
             "massa": lk.get_segment_display(), "vencimento": lk.base_salary}
            for lk in qs]
    return result([col("matricula", "Matrícula"), col("nome", "Nome"), col("cpf", "CPF"), col("sexo", "Sexo"),
                   col("nascimento", "Nascimento", "date"), col("idade", "Idade", "int"), col("orgao", "Órgão"),
                   col("cargo", "Cargo"), col("ingresso", "Ingresso no ente", "date"), col("massa", "Massa"),
                   col("vencimento", "Vencimento base", "money")],
                  rows, {"nome": f"{len(rows)} servidor(es)",
                         "vencimento": sum((r["vencimento"] or ZERO for r in rows), ZERO)})


@report("previsao-aposentadorias", "relatorios.previdenciarios", "Previsão de aposentadorias",
        "Primeira data em que cada servidor ativo cumpre uma regra de aposentadoria voluntária (inclui quem já cumpriu "
        "— candidato ao abono de permanência). Conta o tempo dos vínculos e averbações cadastrados.",
        [{"key": "ate", "label": "Cumpre até o ano", "type": "ano", "default": "atual+5"}, PLANO_FILTER], landscape=True)
def previsao_aposentadorias(inst, p):
    from apps.employment.models import EmploymentLink
    from apps.previdencia.models import RetirementRule
    from apps.previdencia.rules import RuleEvaluator
    from apps.previdencia.services import is_teacher
    from apps.previdencia.tempo import PersonTime

    limit = date(int(p.get("ate") or _today().year + 5), 12, 31)
    rules = [r for r in RetirementRule.objects.filter(institution=inst, active=True) if r.group != "COMPULSORIA"]
    links = (EmploymentLink.objects.filter(institution=inst, regime="ESTATUTARIO", status="ATIVO")
             .select_related("person", "position").order_by("person__name"))
    if p.get("plano"):
        links = links.filter(segment=p["plano"])
    rows, today = [], _today()
    for lk in links:
        pt = PersonTime(lk.person, reference_link=lk)
        ev = RuleEvaluator(lk.person, pt, today=today)
        teacher = is_teacher(pt)
        best = None
        for rule in rules:
            if rule.for_teacher and not teacher:
                continue
            r = ev.evaluate(rule)
            if r.eligible_date and (best is None or r.eligible_date < best[1]):
                best = (rule, r.eligible_date)
        if best and best[1] <= limit:
            rows.append({"nome": lk.person.name, "cpf": _cpf(lk.person.cpf), "cargo": lk.position.name,
                         "idade": _age(lk.person.birth_date), "regra": best[0].name, "fundamento": best[0].legal_basis,
                         "data": best[1], "situacao": "Já cumpre (abono de permanência)" if best[1] <= today
                         else "Cumprirá"})
    rows.sort(key=lambda r: r["data"])
    already = sum(1 for r in rows if r["data"] <= today)
    return result([col("nome", "Nome"), col("cpf", "CPF"), col("cargo", "Cargo"), col("idade", "Idade", "int"),
                   col("regra", "Primeira regra cumprida"), col("fundamento", "Fundamento"),
                   col("data", "Cumpre em", "date"), col("situacao", "Situação")],
                  rows, {"nome": f"{len(rows)} servidor(es) — {already} já cumprem"},
                  ["Estimativa pelo cadastro: confira averbações e tempo especial antes de qualquer orientação ao servidor."])


@report("averbacoes", "relatorios.previdenciarios", "Averbações de tempo de contribuição",
        "Certidões de tempo de outros regimes averbadas (ativas).", [])
def averbacoes(inst, p):
    from apps.previdencia.models import Averbacao

    qs = Averbacao.objects.filter(institution=inst, active=True).select_related("person").order_by("person__name", "start_date")
    rows = [{"nome": a.person.name, "cpf": _cpf(a.person.cpf), "natureza": a.get_nature_display(), "emissor": a.issuer,
             "certidao": a.certificate_number, "inicio": a.start_date, "fim": a.end_date, "dias": a.certified_days,
             "comprev": a.comprev} for a in qs]
    return result([col("nome", "Nome"), col("cpf", "CPF"), col("natureza", "Natureza"), col("emissor", "Emissor"),
                   col("certidao", "Certidão"), col("inicio", "Início", "date"), col("fim", "Fim", "date"),
                   col("dias", "Dias", "int"), col("comprev", "COMPREV", "bool")],
                  rows, {"nome": f"{len(rows)} averbação(ões)", "dias": sum(r["dias"] or 0 for r in rows)})


@report("ctcs", "relatorios.previdenciarios", "Certidões de Tempo de Contribuição emitidas",
        "CTCs emitidas pelo RPPS no período.", PERIOD)
def ctcs(inst, p):
    from apps.previdencia.models import Ctc

    start, end = _period(p)
    qs = (Ctc.objects.filter(institution=inst, created_at__date__gte=start, created_at__date__lte=end)
          .select_related("person").order_by("year", "number"))
    rows = [{"numero": f"{c.number}/{c.year}", "emissao": timezone.localtime(c.created_at).date(), "nome": c.person.name,
             "cpf": _cpf(c.person.cpf), "destino": c.destination, "inicio": c.period_start, "fim": c.period_end,
             "situacao": c.get_status_display()} for c in qs]
    return result([col("numero", "Número"), col("emissao", "Emissão", "date"), col("nome", "Nome"), col("cpf", "CPF"),
                   col("destino", "Destino"), col("inicio", "Período de", "date"), col("fim", "até", "date"),
                   col("situacao", "Situação")], rows, {"numero": f"{len(rows)} certidão(ões)"})


# ================================================================= BENEFÍCIOS
STATUS_FILTER = {"key": "situacao", "label": "Situação", "type": "select", "default": "ATIVO",
                 "options": [["ATIVO", "Ativos"], ["SUSPENSO", "Suspensos"], ["CESSADO", "Cessados"], ["", "Todos"]]}
KIND_FILTER = {"key": "tipo", "label": "Tipo", "type": "select", "default": "",
               "options": [["", "Aposentadorias e pensões"], ["APOSENTADORIA", "Aposentadorias"], ["PENSAO", "Pensões"]]}


@report("beneficios", "relatorios.beneficios", "Benefícios por situação",
        "Aposentadorias e pensões com folha, início, valor, integralidade e paridade.",
        [STATUS_FILTER, KIND_FILTER, PLANO_FILTER], landscape=True)
def beneficios(inst, p):
    from apps.concessao.models import Benefit

    qs = Benefit.objects.filter(institution=inst).select_related("beneficiary", "instituidor", "payroll_group")
    if p.get("situacao"):
        qs = qs.filter(status=p["situacao"])
    if p.get("tipo"):
        qs = qs.filter(kind=p["tipo"])
    if p.get("plano"):
        qs = qs.filter(payroll_group__segment=p["plano"])
    rows = [{"tipo": b.get_kind_display(), "nome": b.beneficiary.name, "cpf": _cpf(b.beneficiary.cpf),
             "instituidor": b.instituidor.name if b.instituidor_id else "", "folha": b.payroll_group.code,
             "inicio": b.start_date, "fim": b.end_date, "valor": b.amount, "integral": b.integralidade,
             "paridade": b.paridade, "situacao": b.get_status_display()}
            for b in qs.order_by("kind", "beneficiary__name")]
    return result([col("tipo", "Tipo"), col("nome", "Beneficiário"), col("cpf", "CPF"), col("instituidor", "Instituidor"),
                   col("folha", "Folha"), col("inicio", "Início", "date"), col("fim", "Fim", "date"),
                   col("valor", "Valor", "money"), col("integral", "Integral", "bool"), col("paridade", "Paridade", "bool"),
                   col("situacao", "Situação")],
                  rows, {"nome": f"{len(rows)} benefício(s)", "valor": sum((r["valor"] for r in rows), ZERO)})


@report("concessoes", "relatorios.beneficios", "Processos de concessão e revisão",
        "Processos abertos no período, com etapa atual, regra e valor apurado.", PERIOD, landscape=True)
def concessoes(inst, p):
    from apps.concessao.models import Concession

    start, end = _period(p)
    qs = (Concession.objects.filter(institution=inst, created_at__date__gte=start, created_at__date__lte=end)
          .select_related("process", "person", "rule").order_by("created_at"))
    rows = [{"processo": c.process.code, "abertura": timezone.localtime(c.created_at).date(), "tipo": c.get_kind_display(),
             "nome": c.person.name, "etapa": c.get_stage_display(), "regra": c.rule.name if c.rule_id else "",
             "validade": c.validity_date, "valor": c.total} for c in qs]
    return result([col("processo", "Processo"), col("abertura", "Abertura", "date"), col("tipo", "Tipo"),
                   col("nome", "Interessado"), col("etapa", "Etapa"), col("regra", "Regra"),
                   col("validade", "Validade", "date"), col("valor", "Valor", "money")],
                  rows, {"processo": f"{len(rows)} processo(s)"})


@report("eventos-beneficios", "relatorios.beneficios", "Eventos de benefícios",
        "Implantações, revisões, suspensões, restabelecimentos, cessações e reversões no período.", PERIOD, landscape=True)
def eventos_beneficios(inst, p):
    from apps.concessao.models import BenefitEvent

    start, end = _period(p)
    qs = (BenefitEvent.objects.filter(institution=inst, date__gte=start, date__lte=end)
          .select_related("benefit__beneficiary").order_by("date"))
    rows = [{"data": e.date, "evento": e.get_kind_display(), "nome": e.benefit.beneficiary.name,
             "beneficio": e.benefit.get_kind_display(), "ato": e.act, "justificativa": e.justification} for e in qs]
    return result([col("data", "Data", "date"), col("evento", "Evento"), col("nome", "Beneficiário"),
                   col("beneficio", "Benefício"), col("ato", "Ato"), col("justificativa", "Justificativa")],
                  rows, {"data": f"{len(rows)} evento(s)"})


@report("cotas-temporarias", "relatorios.beneficios", "Pensões temporárias a vencer",
        "Cotas de pensão com data de término (cônjuge pela idade, filho aos 21 anos).",
        [{"key": "dias", "label": "Vencendo em até (dias)", "type": "select", "default": "365",
          "options": [["90", "90 dias"], ["180", "180 dias"], ["365", "1 ano"], ["", "Todas"]]}])
def cotas_temporarias(inst, p):
    from apps.concessao.models import Benefit

    today = _today()
    qs = (Benefit.objects.filter(institution=inst, kind="PENSAO", status="ATIVO", end_date__isnull=False)
          .select_related("beneficiary", "instituidor").order_by("end_date"))
    if p.get("dias"):
        qs = qs.filter(end_date__lte=today + timedelta(days=int(p["dias"])))
    rows = [{"nome": b.beneficiary.name, "cpf": _cpf(b.beneficiary.cpf),
             "instituidor": b.instituidor.name if b.instituidor_id else "", "fim": b.end_date,
             "dias": (b.end_date - today).days, "valor": b.amount} for b in qs]
    return result([col("nome", "Pensionista"), col("cpf", "CPF"), col("instituidor", "Instituidor"),
                   col("fim", "Término", "date"), col("dias", "Dias restantes", "int"), col("valor", "Valor", "money")],
                  rows, {"nome": f"{len(rows)} cota(s)", "valor": sum((r["valor"] for r in rows), ZERO)})


# ================================================================= FOLHA
@report("resumo-folhas", "relatorios.folha", "Resumo das folhas do ano",
        "Totais de cada folha (mensal e 13º) por competência e massa.", [YEAR, PLANO_FILTER])
def resumo_folhas(inst, p):
    from apps.folha.models import PayrollRun

    qs = (PayrollRun.objects.filter(institution=inst, competence__year=_year(p))
          .select_related("competence", "payroll_group").order_by("competence__month", "payroll_group__code", "kind"))
    if p.get("plano"):
        qs = qs.filter(payroll_group__segment=p["plano"])
    rows = []
    for r in qs:
        t = r.totals or {}
        rows.append({"competencia": f"{r.competence.month:02d}/{r.competence.year}", "folha": r.payroll_group.code,
                     "tipo": r.get_kind_display(), "situacao": r.get_status_display(),
                     "beneficiarios": t.get("beneficiarios", 0), "proventos": _money(t.get("proventos")),
                     "descontos": _money(t.get("descontos")), "liquido": _money(t.get("liquido"))})
    return result([col("competencia", "Competência"), col("folha", "Folha"), col("tipo", "Tipo"),
                   col("situacao", "Situação"), col("beneficiarios", "Beneficiários", "int"),
                   col("proventos", "Proventos", "money"), col("descontos", "Descontos", "money"),
                   col("liquido", "Líquido", "money")],
                  rows, {k: sum((r[k] for r in rows), ZERO) for k in ("proventos", "descontos", "liquido")}
                  | {"competencia": f"{len(rows)} folha(s)"})


def _entries(inst, p):
    from apps.folha.models import PayrollEntry

    y, m = _competence(inst, p)
    qs = PayrollEntry.objects.filter(institution=inst, run__competence__year=y, run__competence__month=m)
    if p.get("plano"):
        qs = qs.filter(run__payroll_group__segment=p["plano"])
    if p.get("tipo_folha"):
        qs = qs.filter(run__kind=p["tipo_folha"])
    return qs, f"{m:02d}/{y}"


RUN_KIND = {"key": "tipo_folha", "label": "Tipo de folha", "type": "select", "default": "MENSAL",
            "options": [["MENSAL", "Mensal"], ["DECIMO", "13º"], ["", "Todas"]]}


@report("rubricas", "relatorios.folha", "Totais por rubrica",
        "Quantidade de lançamentos e valor total de cada rubrica na competência.", [COMP, RUN_KIND, PLANO_FILTER])
def rubricas(inst, p):
    from apps.folha.models import PayrollItem

    entries, label = _entries(inst, p)
    agg = (PayrollItem.objects.filter(entry__in=entries).values("code", "name", "kind")
           .annotate(qtd=Count("id"), total=Sum("amount")).order_by("kind", "code"))
    kinds = {"PROVENTO": "Provento", "DESCONTO": "Desconto", "INFORMATIVA": "Informativa"}
    rows = [{"codigo": a["code"], "rubrica": a["name"], "tipo": kinds.get(a["kind"], a["kind"]), "qtd": a["qtd"],
             "total": a["total"] or ZERO} for a in agg]
    prov = sum((r["total"] for r in rows if r["tipo"] == "Provento"), ZERO)
    desc = sum((r["total"] for r in rows if r["tipo"] == "Desconto"), ZERO)
    return result([col("codigo", "Código"), col("rubrica", "Rubrica"), col("tipo", "Tipo"), col("qtd", "Lançamentos", "int"),
                   col("total", "Total", "money")], rows,
                  {"rubrica": f"Competência {label}"},
                  [f"Proventos: R$ {prov:,.2f} · Descontos: R$ {desc:,.2f} · Líquido: R$ {prov - desc:,.2f}"
                   .replace(",", "X").replace(".", ",").replace("X", ".")])


@report("liquidos", "relatorios.folha", "Relação de líquidos por beneficiário",
        "Bruto, descontos, líquido e conta de crédito de cada contracheque da competência.",
        [COMP, RUN_KIND, PLANO_FILTER], landscape=True)
def liquidos(inst, p):
    entries, label = _entries(inst, p)
    rows = []
    for e in entries.select_related("beneficiary", "run__payroll_group").order_by("beneficiary__name"):
        b = e.bank or {}
        conta = f"{b.get('banco', '')} ag. {b.get('agencia', '')} c/c {b.get('conta', '')}-{b.get('conta_dv', '')}" if b else "SEM CONTA"
        rows.append({"nome": e.beneficiary.name, "cpf": _cpf(e.beneficiary.cpf), "folha": e.run.payroll_group.code,
                     "bruto": e.gross, "descontos": e.discounts, "liquido": e.net, "conta": conta})
    return result([col("nome", "Beneficiário"), col("cpf", "CPF"), col("folha", "Folha"), col("bruto", "Bruto", "money"),
                   col("descontos", "Descontos", "money"), col("liquido", "Líquido", "money"), col("conta", "Crédito")],
                  rows, {"nome": f"{len(rows)} contracheque(s) — {label}"}
                  | {k: sum((r[k] for r in rows), ZERO) for k in ("bruto", "descontos", "liquido")})


@report("retencoes", "relatorios.folha", "Contribuição previdenciária e IRRF retidos",
        "Bases e valores retidos dos beneficiários em cada competência do ano (para conferência com a DCTFWeb/EFD-Reinf "
        "e o repasse ao RPPS).", [YEAR, PLANO_FILTER])
def retencoes(inst, p):
    from apps.folha.models import PayrollEntry, PayrollItem

    y = _year(p)
    entries = PayrollEntry.objects.filter(institution=inst, run__competence__year=y)
    if p.get("plano"):
        entries = entries.filter(run__payroll_group__segment=p["plano"])
    bases = {(r["run__competence__month"], r["run__kind"]): r for r in entries.values("run__competence__month", "run__kind")
             .annotate(rpps=Sum("rpps_base"), ir=Sum("ir_base"))}
    items = (PayrollItem.objects.filter(entry__in=entries, rubric__calc__in=["CONTRIB_RPPS", "CONTRIB_13", "IRRF", "IRRF_13", "IRRF_RRA"])
             .values("entry__run__competence__month", "entry__run__kind", "rubric__calc").annotate(total=Sum("amount")))
    acc = defaultdict(lambda: {"contrib": ZERO, "irrf": ZERO})
    for i in items:
        k = (i["entry__run__competence__month"], i["entry__run__kind"])
        acc[k]["contrib" if i["rubric__calc"].startswith("CONTRIB") else "irrf"] += i["total"] or ZERO
    rows = []
    for k in sorted(set(bases) | set(acc)):
        rows.append({"competencia": f"{k[0]:02d}/{y}" + (" (13º)" if k[1] == "DECIMO" else ""),
                     "base_rpps": bases.get(k, {}).get("rpps") or ZERO, "contribuicao": acc[k]["contrib"],
                     "base_ir": bases.get(k, {}).get("ir") or ZERO, "irrf": acc[k]["irrf"]})
    return result([col("competencia", "Competência"), col("base_rpps", "Base contribuição", "money"),
                   col("contribuicao", "Contribuição retida", "money"), col("base_ir", "Base IR", "money"),
                   col("irrf", "IRRF retido", "money")],
                  rows, {k: sum((r[k] for r in rows), ZERO) for k in ("base_rpps", "contribuicao", "base_ir", "irrf")})


# ================================================================= FINANCEIROS
FIN_PLAN = {"key": "plano", "label": "Plano", "type": "select", "default": "",
            "options": [["", "Todos"], ["FINANCEIRO", "Financeiro"], ["PREVIDENCIARIO", "Previdenciário"]]}


@report("receitas", "relatorios.financeiros", "Receitas realizadas",
        "Receitas baixadas no período (contribuições, aportes, parcelamentos, COMPREV, rendimentos e outras).",
        PERIOD + [FIN_PLAN], landscape=True)
def receitas(inst, p):
    from apps.financeiro.models import Revenue

    start, end = _period(p)
    qs = (Revenue.objects.filter(institution=inst, active=True, date__gte=start, date__lte=end)
          .select_related("plan", "account__bank").order_by("date"))
    if p.get("plano"):
        qs = qs.filter(plan__kind=p["plano"])
    rows = [{"data": r.date, "competencia": f"{r.competence:%m/%Y}" if r.competence else "", "tipo": r.get_kind_display(),
             "plano": r.plan.code, "conta": f"{r.account.bank.code} {r.account.account}" if r.account_id else "",
             "descricao": r.description, "valor": r.amount, "acrescimos": r.fines} for r in qs]
    return result([col("data", "Data", "date"), col("competencia", "Competência"), col("tipo", "Tipo"), col("plano", "Plano"),
                   col("conta", "Conta"), col("descricao", "Descrição"), col("valor", "Valor", "money"),
                   col("acrescimos", "Multa/juros", "money")],
                  rows, {"data": f"{len(rows)} lançamento(s)", "valor": sum((r["valor"] for r in rows), ZERO),
                         "acrescimos": sum((r["acrescimos"] or ZERO for r in rows), ZERO)})


@report("contribuicoes", "relatorios.financeiros", "Contribuições devidas x recebidas",
        "Contribuições lançadas (servidor, patronal, aposentados) e o que já foi recebido, por competência do ano.",
        [YEAR, FIN_PLAN], landscape=True)
def contribuicoes(inst, p):
    from apps.financeiro.models import Contribution

    qs = (Contribution.objects.filter(institution=inst, active=True, competence__year=_year(p))
          .select_related("plan", "organ").annotate(recebido=Sum("payments__amount", filter=Q(payments__active=True)))
          .order_by("competence", "organ__name", "kind"))
    if p.get("plano"):
        qs = qs.filter(plan__kind=p["plano"])
    rows = [{"competencia": f"{c.competence:%m/%Y}", "orgao": c.organ.short_name or c.organ.name if c.organ_id else "",
             "tipo": c.get_kind_display(), "plano": c.plan.code, "vencimento": c.due_date, "devido": c.amount,
             "recebido": c.recebido or ZERO, "saldo": c.amount - (c.recebido or ZERO)} for c in qs]
    return result([col("competencia", "Competência"), col("orgao", "Órgão"), col("tipo", "Tipo"), col("plano", "Plano"),
                   col("vencimento", "Vencimento", "date"), col("devido", "Devido", "money"),
                   col("recebido", "Recebido", "money"), col("saldo", "Saldo", "money")],
                  rows, {k: sum((r[k] for r in rows), ZERO) for k in ("devido", "recebido", "saldo")})


@report("parcelamentos", "relatorios.financeiros", "Parcelamentos",
        "Acordos de parcelamento com parcelas pagas e em aberto (valores nominais).", [FIN_PLAN], landscape=True)
def parcelamentos(inst, p):
    from apps.financeiro.models import InstallmentAgreement

    qs = InstallmentAgreement.objects.filter(institution=inst).select_related("plan", "organ").order_by("signed_date")
    if p.get("plano"):
        qs = qs.filter(plan__kind=p["plano"])
    rows, today = [], _today()
    for a in qs:
        inst_qs = a.parcels.all()
        paid = inst_qs.filter(payments__active=True).distinct()
        open_ = inst_qs.exclude(pk__in=paid)
        rows.append({"numero": a.number, "orgao": a.organ.short_name or a.organ.name if a.organ_id else "",
                     "plano": a.plan.code, "assinatura": a.signed_date, "principal": a.principal,
                     "parcelas": a.installments, "pagas": paid.count(),
                     "vencidas": open_.filter(due_date__lt=today).count(),
                     "aberto": open_.aggregate(s=Sum("amount"))["s"] or ZERO, "situacao": a.get_status_display()})
    return result([col("numero", "Acordo"), col("orgao", "Órgão"), col("plano", "Plano"), col("assinatura", "Assinatura", "date"),
                   col("principal", "Principal", "money"), col("parcelas", "Parcelas", "int"), col("pagas", "Pagas", "int"),
                   col("vencidas", "Vencidas em aberto", "int"), col("aberto", "Saldo em aberto", "money"),
                   col("situacao", "Situação")],
                  rows, {"principal": sum((r["principal"] for r in rows), ZERO), "aberto": sum((r["aberto"] for r in rows), ZERO)},
                  ["Valores nominais do cronograma — a atualização monetária das parcelas ainda não é automática."])


@report("pagamentos", "relatorios.financeiros", "Lotes de pagamento da folha",
        "Lotes gerados a partir das folhas fechadas, com situação e totais.", [YEAR, FIN_PLAN])
def pagamentos(inst, p):
    from apps.financeiro.models import PaymentBatch

    qs = (PaymentBatch.objects.filter(institution=inst, payroll_run__competence__year=_year(p))
          .select_related("payroll_run__competence", "payroll_run__payroll_group", "plan").order_by("number"))
    if p.get("plano"):
        qs = qs.filter(plan__kind=p["plano"])
    rows = [{"lote": b.number, "competencia": f"{b.payroll_run.competence.month:02d}/{b.payroll_run.competence.year}",
             "folha": b.payroll_run.payroll_group.code, "pagamento": b.payment_date, "situacao": b.get_status_display(),
             "itens": b.items_count, "total": b.total} for b in qs]
    return result([col("lote", "Lote", "int"), col("competencia", "Competência"), col("folha", "Folha"),
                   col("pagamento", "Pagamento", "date"), col("situacao", "Situação"), col("itens", "Créditos", "int"),
                   col("total", "Total", "money")], rows, {"total": sum((r["total"] for r in rows), ZERO)})


# ================================================================= GERENCIAIS
@report("quadro-geral", "relatorios.gerenciais", "Quadro geral por massa",
        "Servidores ativos, aposentados, pensionistas e a última folha calculada de cada massa.", [])
def quadro_geral(inst, p):
    from apps.concessao.models import Benefit
    from apps.employment.models import EmploymentLink
    from apps.folha.models import PayrollRun
    from apps.institutions.models import PayrollGroup

    rows = []
    for g in PayrollGroup.objects.filter(institution=inst, active=True).order_by("code"):
        ben = Benefit.objects.filter(institution=inst, payroll_group=g, status="ATIVO")
        run = (PayrollRun.objects.filter(institution=inst, payroll_group=g, kind="MENSAL").exclude(status="ABERTA")
               .select_related("competence").order_by("-competence__year", "-competence__month").first())
        t = (run.totals or {}) if run else {}
        rows.append({"massa": g.name, "ativos": EmploymentLink.objects.filter(institution=inst, regime="ESTATUTARIO",
                                                                             status="ATIVO", segment=g.segment).count(),
                     "aposentados": ben.filter(kind="APOSENTADORIA").count(), "pensionistas": ben.filter(kind="PENSAO").count(),
                     "competencia": f"{run.competence.month:02d}/{run.competence.year}" if run else "—",
                     "bruta": _money(t.get("proventos")), "liquida": _money(t.get("liquido"))})
    tot = {k: sum(r[k] for r in rows) for k in ("ativos", "aposentados", "pensionistas")}
    tot |= {k: sum((r[k] for r in rows), ZERO) for k in ("bruta", "liquida")}
    return result([col("massa", "Massa"), col("ativos", "Servidores ativos", "int"), col("aposentados", "Aposentados", "int"),
                   col("pensionistas", "Pensionistas", "int"), col("competencia", "Última folha"),
                   col("bruta", "Folha bruta", "money"), col("liquida", "Folha líquida", "money")], rows, tot)


@report("protocolo-prazos", "relatorios.gerenciais", "Processos do Protocolo e prazos",
        "Processos em andamento com setor atual, vencimento e atraso.",
        [{"key": "so_atrasados", "label": "Mostrar", "type": "select", "default": "",
          "options": [["", "Todos os abertos"], ["1", "Só atrasados"]]}], landscape=True)
def protocolo_prazos(inst, p):
    from apps.protocolo.models import OPEN_STATUSES, Process

    today = _today()
    qs = (Process.objects.filter(institution=inst, status__in=OPEN_STATUSES)
          .select_related("process_type", "current_sector").order_by("due_date"))
    if p.get("so_atrasados"):
        qs = qs.filter(due_date__lt=today, suspended_since__isnull=True)
    rows = [{"processo": pr.code, "tipo": pr.process_type.name, "interessado": pr.interested_name, "setor": pr.current_sector.code,
             "abertura": pr.opened_date, "vencimento": pr.due_date, "dias": (pr.due_date - today).days if pr.due_date else None,
             "situacao": pr.get_status_display()} for pr in qs]
    late = sum(1 for r in rows if r["dias"] is not None and r["dias"] < 0 and r["situacao"] != "Sobrestado")
    return result([col("processo", "Processo"), col("tipo", "Tipo"), col("interessado", "Interessado"), col("setor", "Setor"),
                   col("abertura", "Abertura", "date"), col("vencimento", "Vencimento", "date"),
                   col("dias", "Dias restantes", "int"), col("situacao", "Situação")],
                  rows, {"processo": f"{len(rows)} processo(s) — {late} atrasado(s)"},
                  ["Dias restantes negativos = atraso (dias úteis ou corridos conforme o tipo de processo)."])


@report("concessoes-etapa", "relatorios.gerenciais", "Concessões por etapa",
        "Quantidade de processos de concessão em cada etapa e há quantos dias estão abertos (média).", [])
def concessoes_etapa(inst, p):
    from apps.concessao.models import Concession, Stage

    today = _today()
    acc = defaultdict(lambda: {"qtd": 0, "dias": 0})
    for c in Concession.objects.filter(institution=inst).only("kind", "stage", "created_at"):
        a = acc[(c.kind, c.stage)]
        a["qtd"] += 1
        a["dias"] += (today - timezone.localtime(c.created_at).date()).days
    kinds = {"APOSENTADORIA": "Aposentadoria", "PENSAO": "Pensão", "REVISAO": "Revisão"}
    rows = [{"tipo": kinds.get(k, k), "etapa": Stage(s).label, "qtd": v["qtd"], "media": round(v["dias"] / v["qtd"])}
            for (k, s), v in sorted(acc.items())]
    return result([col("tipo", "Tipo"), col("etapa", "Etapa"), col("qtd", "Processos", "int"),
                   col("media", "Dias em aberto (média)", "int")], rows, {"qtd": sum(r["qtd"] for r in rows)})


# ================================================================= ESTATÍSTICOS
AGE_BANDS = [(0, 30, "Até 30"), (31, 40, "31 a 40"), (41, 50, "41 a 50"), (51, 60, "51 a 60"), (61, 70, "61 a 70"),
             (71, 80, "71 a 80"), (81, 200, "81 ou mais")]


def _band(age):
    for lo, hi, label in AGE_BANDS:
        if age is not None and lo <= age <= hi:
            return label
    return "Sem data de nascimento"


@report("faixa-etaria", "relatorios.estatisticos", "Distribuição por faixa etária e sexo",
        "Servidores ativos, aposentados e pensionistas por faixa de idade (F = feminino, M = masculino).",
        [PLANO_FILTER], landscape=True)
def faixa_etaria(inst, p):
    from apps.concessao.models import Benefit
    from apps.employment.models import EmploymentLink

    links = EmploymentLink.objects.filter(institution=inst, regime="ESTATUTARIO", status="ATIVO").select_related("person")
    bens = Benefit.objects.filter(institution=inst, status="ATIVO").select_related("beneficiary")
    if p.get("plano"):
        links = links.filter(segment=p["plano"])
        bens = bens.filter(payroll_group__segment=p["plano"])
    cnt = defaultdict(int)
    for lk in links:
        cnt[(_band(_age(lk.person.birth_date)), "at", SEX.get(lk.person.sex, "M"))] += 1
    for b in bens:
        g = "ap" if b.kind == "APOSENTADORIA" else "pe"
        cnt[(_band(_age(b.beneficiary.birth_date)), g, SEX.get(b.beneficiary.sex, "M"))] += 1
    labels = [b[2] for b in AGE_BANDS] + ["Sem data de nascimento"]
    rows = []
    for lb in labels:
        r = {"faixa": lb}
        for g in ("at", "ap", "pe"):
            for s in ("F", "M"):
                r[f"{g}_{s}"] = cnt[(lb, g, s)]
        r["total"] = sum(v for k, v in r.items() if k != "faixa")
        if r["total"] or lb != labels[-1]:
            rows.append(r)
    keys = [f"{g}_{s}" for g in ("at", "ap", "pe") for s in ("F", "M")] + ["total"]
    return result([col("faixa", "Faixa etária"), col("at_F", "Ativos F", "int"), col("at_M", "Ativos M", "int"),
                   col("ap_F", "Aposentados F", "int"), col("ap_M", "Aposentados M", "int"),
                   col("pe_F", "Pensionistas F", "int"), col("pe_M", "Pensionistas M", "int"), col("total", "Total", "int")],
                  rows, {k: sum(r[k] for r in rows) for k in keys})


@report("faixa-valor", "relatorios.estatisticos", "Benefícios por faixa de valor",
        "Aposentadorias e pensões ativas por faixa em salários mínimos (salário mínimo vigente em Parâmetros).",
        [PLANO_FILTER])
def faixa_valor(inst, p):
    from apps.concessao.models import Benefit
    from apps.institutions.services import get_parameter

    sm = _money(get_parameter(inst, "salario_minimo"))
    if not sm:
        raise BusinessRuleError("Cadastre o salário mínimo vigente em Parâmetros (salario_minimo).")
    bands = [(0, 1, "Até 1 SM"), (1, 2, "Mais de 1 a 2 SM"), (2, 3, "Mais de 2 a 3 SM"), (3, 5, "Mais de 3 a 5 SM"),
             (5, 10, "Mais de 5 a 10 SM"), (10, 10 ** 6, "Mais de 10 SM")]
    qs = Benefit.objects.filter(institution=inst, status="ATIVO")
    if p.get("plano"):
        qs = qs.filter(payroll_group__segment=p["plano"])
    acc = {b[2]: {"ap": 0, "ap_v": ZERO, "pe": 0, "pe_v": ZERO} for b in bands}
    for b in qs.only("kind", "amount"):
        q = b.amount / sm
        lb = next(label for lo, hi, label in bands if (q <= hi and (q > lo or lo == 0)))
        g = "ap" if b.kind == "APOSENTADORIA" else "pe"
        acc[lb][g] += 1
        acc[lb][f"{g}_v"] += b.amount
    rows = [{"faixa": lb, "aposentadorias": v["ap"], "valor_ap": v["ap_v"], "pensoes": v["pe"], "valor_pe": v["pe_v"]}
            for lb, v in acc.items()]
    return result([col("faixa", "Faixa"), col("aposentadorias", "Aposentadorias", "int"), col("valor_ap", "Valor", "money"),
                   col("pensoes", "Pensões", "int"), col("valor_pe", "Valor", "money")],
                  rows, {k: sum((r[k] for r in rows), ZERO if k.startswith("valor") else 0)
                         for k in ("aposentadorias", "valor_ap", "pensoes", "valor_pe")},
                  [f"Salário mínimo considerado: R$ {sm:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")])


@report("cargos", "relatorios.estatisticos", "Servidores ativos por cargo",
        "Quantidade, idade média, vencimento médio e participação feminina por cargo.", [PLANO_FILTER])
def cargos(inst, p):
    from apps.employment.models import EmploymentLink

    qs = EmploymentLink.objects.filter(institution=inst, regime="ESTATUTARIO", status="ATIVO").select_related("person", "position")
    if p.get("plano"):
        qs = qs.filter(segment=p["plano"])
    acc = defaultdict(lambda: {"n": 0, "idade": 0, "ni": 0, "sal": ZERO, "ns": 0, "f": 0})
    for lk in qs:
        a = acc[lk.position.name]
        a["n"] += 1
        age = _age(lk.person.birth_date)
        if age is not None:
            a["idade"] += age
            a["ni"] += 1
        if lk.base_salary:
            a["sal"] += lk.base_salary
            a["ns"] += 1
        a["f"] += lk.person.sex == 1
    rows = [{"cargo": k, "qtd": a["n"], "idade": round(a["idade"] / a["ni"]) if a["ni"] else None,
             "salario": (a["sal"] / a["ns"]).quantize(Decimal("0.01")) if a["ns"] else None,
             "mulheres": (Decimal(a["f"]) * 100 / a["n"]).quantize(Decimal("0.1"))}
            for k, a in sorted(acc.items(), key=lambda kv: -kv[1]["n"])]
    return result([col("cargo", "Cargo"), col("qtd", "Servidores", "int"), col("idade", "Idade média", "int"),
                   col("salario", "Vencimento médio", "money"), col("mulheres", "% mulheres", "percent")],
                  rows, {"qtd": sum(r["qtd"] for r in rows)})


# ================================================================= eSOCIAL
ES_STATUS = ["PENDENTE", "VALIDADO", "EXPORTADO", "ACEITO", "REJEITADO", "SUBSTITUIDO"]


@report("esocial-eventos", "relatorios.esocial", "Eventos do eSocial por situação",
        "Quantidade de eventos de cada tipo em cada situação (pendente, validado, exportado, aceito, rejeitado).",
        [{"key": "periodo", "label": "Período de apuração (AAAA-MM)", "type": "competencia", "default": ""}])
def esocial_eventos(inst, p):
    from apps.esocial.models import EsocialEvent

    qs = EsocialEvent.objects.filter(institution=inst)
    if p.get("periodo"):
        qs = qs.filter(period=p["periodo"])
    acc = defaultdict(lambda: defaultdict(int))
    for r in qs.values("event_type", "status").annotate(n=Count("id")):
        acc[r["event_type"]][r["status"]] = r["n"]
    rows = [{"tipo": t, **{s.lower(): acc[t][s] for s in ES_STATUS}, "total": sum(acc[t].values())} for t in sorted(acc)]
    keys = [s.lower() for s in ES_STATUS] + ["total"]
    return result([col("tipo", "Evento")] + [col(s.lower(), s.capitalize(), "int") for s in ES_STATUS]
                  + [col("total", "Total", "int")], rows, {k: sum(r[k] for r in rows) for k in keys})


@report("esocial-rejeicoes", "relatorios.esocial", "Eventos rejeitados pelo eSocial",
        "Eventos com retorno de erro, com o código e a mensagem do governo, para correção.", [], landscape=True)
def esocial_rejeicoes(inst, p):
    from apps.esocial.models import EsocialEvent

    qs = EsocialEvent.objects.filter(institution=inst, status="REJEITADO").order_by("-returned_at")
    rows = [{"tipo": e.event_type, "referencia": e.reference, "cpf": _cpf(e.cpf), "periodo": e.period,
             "codigo": e.return_code, "mensagem": e.return_message,
             "retorno": timezone.localtime(e.returned_at).date() if e.returned_at else None} for e in qs]
    return result([col("tipo", "Evento"), col("referencia", "Referência"), col("cpf", "CPF"), col("periodo", "Período"),
                   col("codigo", "Código"), col("mensagem", "Mensagem do eSocial"), col("retorno", "Retorno", "date")],
                  rows, {"tipo": f"{len(rows)} rejeição(ões)"})
