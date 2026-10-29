"""
Motor de cálculo da folha de benefícios.

Folha MENSAL, por benefício (ligado à folha/massa da execução):
  1. Proventos/pensão proporcionais aos dias do mês (mês comercial de 30 dias).
  2. Retroativo: benefício concedido no SIST (processo de concessão) que nunca entrou numa folha fechada recebe os meses
     desde o início. Meses do ano corrente somam-se ao mês; meses de anos anteriores são tributados como
     rendimentos recebidos acumuladamente (RRA, Lei 7.713/1988, art. 12-A).
  3. Lançamentos (diferenças/reposições) vigentes na competência.
  4. Contribuição ao RPPS: alíquota sobre o que excede o teto do RGPS. Na pensão, o teto é aplicado ao total
     da pensão (soma das cotas do mesmo instituidor) e a contribuição é rateada entre as cotas.
  5. IRRF por BENEFICIÁRIO (soma de todos os seus benefícios na folha), rateado entre os benefícios.
  6. Pensão alimentícia (dedutível do IR; base bruta ou líquida — cálculo iterativo).
  7. Consignações, respeitando a margem consignável (parâmetro 'folha.margem_consignavel').

Folha de 13º: avos (meses com 15 dias ou mais de benefício no ano) × valor do benefício / 12, com
contribuição e IRRF de tributação exclusiva.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from apps.core.exceptions import BusinessRuleError

from .models import AUTOMATIC_CALCS, Entry, IrExemption, PayrollEntry, Rubric, RubricKind, RunKind, RunStatus
from .tax import ZERO, IrTable, compute_ir, contribution, margin_on, q, rate_on


# ------------------------------------------------------------------ datas
def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def months_between(start: date, end_exclusive: date):
    """Primeiros dias dos meses de start (inclusive) até end_exclusive (exclusive)."""
    y, m = start.year, start.month
    while date(y, m, 1) < end_exclusive:
        yield date(y, m, 1)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def paid_days(start: date, end: date | None, m0: date, m1: date) -> int:
    """Dias comerciais (0 a 30) de benefício no mês."""
    if start > m1 or (end is not None and end < m0):
        return 0
    first = min(start.day, 30) if start >= m0 else 1
    last = 30 if end is None or end >= m1 else min(end.day, 30)
    return max(0, last - first + 1)


def prorate(amount: Decimal, days: int) -> Decimal:
    return amount if days >= 30 else q(amount * days / 30)


def add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


# ------------------------------------------------------------------ rubricas
class RubricSet:
    def __init__(self, institution, on: date):
        qs = (Rubric.objects.filter(institution=institution, active=True, valid_from__lte=on)
              .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on)).order_by("code", "-version"))
        self.by_code: dict[str, Rubric] = {}
        for r in qs:
            self.by_code.setdefault(r.code, r)
        self._by_calc = {r.calc: r for r in self.by_code.values() if r.calc in AUTOMATIC_CALCS}
        self.on = on

    def calc(self, calc: str) -> Rubric:
        r = self._by_calc.get(calc)
        if r is None:
            from .models import RubricCalc

            raise BusinessRuleError(f"Não há rubrica vigente em {self.on:%m/%Y} para '{RubricCalc(calc).label}'. "
                                    "Cadastre em Folha › Rubricas (ou rode 'seed_payroll').")
        return r

    def code(self, code: str) -> Rubric | None:
        return self.by_code.get(code)


# ------------------------------------------------------------------ estruturas
@dataclass
class Line:
    rubric: Rubric
    amount: Decimal
    reference: str = ""
    source_entry: Entry | None = None
    name: str = ""


@dataclass
class Slip:
    """Contracheque em montagem (um por benefício)."""
    benefit: object
    lines: list = field(default_factory=list)
    memory: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    # bases
    benefit_value: Decimal = ZERO       # proventos/pensão do mês (proporcional)
    taxable: Decimal = ZERO             # tributável no mês (ano corrente)
    pension_income: Decimal = ZERO      # parte do tributável que é aposentadoria/pensão (parcela isenta 65+)
    rpps_base: Decimal = ZERO
    margin_base: Decimal = ZERO
    contrib: Decimal = ZERO
    rra_income: Decimal = ZERO
    rra_contrib: Decimal = ZERO
    rra_months: int = 0

    def add(self, rubric, amount, reference="", source_entry=None, name=""):
        amount = q(amount)
        if amount == 0:
            return
        self.lines.append(Line(rubric, amount, reference, source_entry, name or rubric.name))

    def total(self, kind) -> Decimal:
        return sum((ln.amount for ln in self.lines if ln.rubric.kind == kind), ZERO)


class Context:
    def __init__(self, run):
        self.run = run
        self.institution = run.institution
        comp = run.competence
        self.m0, self.m1 = month_bounds(comp.year, comp.month)
        self.rubrics = RubricSet(self.institution, self.m0)
        self.ir = IrTable.load(self.institution, self.m0)
        self.rate = rate_on(self.institution, self.m0)
        self.margin = margin_on(self.institution, self.m0)
        self.warnings: list[str] = []
        self._ceilings: dict[int, Decimal] = {}

    def ceiling(self, on: date) -> Decimal:
        from apps.concessao.services import rgps_ceiling

        if on.year not in self._ceilings:
            value, warn = rgps_ceiling(self.institution, on)
            self._ceilings[on.year] = value
            for w in warn:
                if w not in self.warnings:
                    self.warnings.append(w)
        return self._ceilings[on.year]


# ------------------------------------------------------------------ seleção de benefícios
def benefits_for(ctx: Context):
    from apps.concessao.models import Benefit, BenefitStatus

    qs = (Benefit.objects.filter(institution=ctx.institution, payroll_group=ctx.run.payroll_group,
                                 start_date__lte=ctx.m1)
          .filter(Q(end_date__isnull=True) | Q(end_date__gte=ctx.m0 if ctx.run.kind == RunKind.MENSAL
                                                 else date(ctx.m0.year, 1, 1)))
          .select_related("beneficiary", "instituidor").order_by("beneficiary__name"))
    out, suspended = [], []
    for b in qs:
        if b.status == BenefitStatus.SUSPENSO:
            suspended.append(b)
        elif b.status == BenefitStatus.ATIVO or b.end_date is not None:
            out.append(b)
    if suspended:
        ctx.warnings.append(f"{len(suspended)} benefício(s) suspenso(s) fora da folha: "
                            + ", ".join(b.beneficiary.name for b in suspended[:10])
                            + ("…" if len(suspended) > 10 else ""))
    return out


def _entries(ctx: Context, benefit, calcs: set[str]):
    rows = (Entry.objects.filter(institution=ctx.institution, benefit=benefit, active=True, start__lte=ctx.m0)
            .filter(Q(end__isnull=True) | Q(end__gte=ctx.m0)).select_related("consignee")
            .order_by("start", "created_at"))
    out = []
    for e in rows:
        if e.installments and e.paid_installments >= e.installments:
            continue
        r = ctx.rubrics.code(e.rubric_code)
        if r is None:
            ctx.warnings.append(f"Lançamento de {benefit.beneficiary.name}: rubrica {e.rubric_code} sem versão vigente.")
            continue
        if r.calc in calcs:
            out.append((e, r))
    return out


def _installment_ref(e: Entry) -> str:
    return f"{e.paid_installments + 1}/{e.installments}" if e.installments else ""


# ------------------------------------------------------------------ folha mensal
def _has_prior_payroll(benefit, run) -> bool:
    return PayrollEntry.objects.filter(benefit=benefit, run__kind=RunKind.MENSAL,
                                       run__status__in=[RunStatus.FECHADA, RunStatus.PAGA]).exclude(run=run).exists()


def _monthly_base(ctx: Context, b) -> Slip:
    s = Slip(benefit=b)
    days = paid_days(b.start_date, b.end_date, ctx.m0, ctx.m1)
    rub = ctx.rubrics.calc("PENSAO" if b.kind == "PENSAO" else "APOSENTADORIA")
    s.benefit_value = prorate(b.amount, days)
    s.add(rub, s.benefit_value, reference=f"{days} dias" if days < 30 else "")
    s.memory["dias"] = days

    # Retroativo (somente benefícios concedidos no SIST, na primeira folha). Benefício que o sistema anterior já
    # pagou (processo digitalizado) só tem retroativo depois de `paid_until`.
    retro_from = b.start_date
    if b.paid_until:
        nxt = b.paid_until.replace(day=1)
        retro_from = max(retro_from, date(nxt.year + nxt.month // 12, nxt.month % 12 + 1, 1))
    if b.concession_id is not None and retro_from < ctx.m0 and not _has_prior_payroll(b, ctx.run):
        retro_rub = ctx.rubrics.calc("RETROATIVO")
        cur, prev = ZERO, ZERO
        months = []
        for m in months_between(retro_from, ctx.m0):
            mm0, mm1 = month_bounds(m.year, m.month)
            d = paid_days(b.start_date, b.end_date, mm0, mm1)
            v = prorate(b.amount, d)
            c = contribution(v, ctx.ceiling(mm0), ctx.rate) if retro_rub.inc_rpps else ZERO
            months.append({"competencia": f"{m.month:02d}/{m.year}", "dias": d, "valor": str(v), "contribuicao": str(c)})
            if m.year == ctx.m0.year:
                cur += v
                s.contrib += c
            else:
                prev += v
                s.rra_contrib += c
                s.rra_months += 1
        s.memory["retroativo"] = months
        if cur:
            s.add(retro_rub, cur, reference=f"{sum(1 for x in months if x['competencia'].endswith(str(ctx.m0.year)))} mês(es)")
            if retro_rub.inc_ir:
                s.taxable += cur
                s.pension_income += cur
        if prev:
            s.add(retro_rub, prev, reference=f"RRA {s.rra_months} mês(es)", name=f"{retro_rub.name} (anos anteriores)")
            s.rra_income = prev
            s.warnings.append("Retroativo de anos anteriores: 13º desses anos não incluído — lance como diferença.")

    if rub.inc_ir:
        s.taxable += s.benefit_value
        s.pension_income += s.benefit_value
    if rub.inc_rpps:
        s.rpps_base += s.benefit_value
    if rub.inc_margem:
        s.margin_base += s.benefit_value

    for e, r in _entries(ctx, b, {"MANUAL"}):
        value = e.amount if e.amount is not None else q(s.benefit_value * e.percent / 100)
        s.add(r, value, reference=_installment_ref(e), source_entry=e,
              name=f"{r.name} — {e.description}" if e.description else "")
        sign = 1 if r.kind == RubricKind.PROVENTO else -1 if r.kind == RubricKind.DESCONTO else 0
        if r.inc_ir:
            s.taxable += sign * q(value)
        if r.inc_rpps:
            s.rpps_base += sign * q(value)
        if r.inc_margem:
            s.margin_base += sign * q(value)
    return s


def _contributions(ctx: Context, slips: list[Slip], decimo: bool = False):
    """Contribuição: teto aplicado por aposentadoria e pelo total de cada pensão (rateio entre cotas)."""
    rub = ctx.rubrics.calc("CONTRIB_13" if decimo else "CONTRIB_RPPS")
    ceiling = ctx.ceiling(ctx.m0)
    groups: dict = defaultdict(list)
    for s in slips:
        key = ("P", s.benefit.instituidor_id) if s.benefit.kind == "PENSAO" else ("A", s.benefit.pk)
        groups[key].append(s)
    for items in groups.values():
        total = sum((s.rpps_base for s in items), ZERO)
        value = contribution(total, ceiling, ctx.rate)
        shares = _split(value, [s.rpps_base for s in items])
        for s, share in zip(items, shares):
            s.contrib += share
            s.memory["contribuicao"] = {"base": str(s.rpps_base), "teto": str(ceiling), "aliquota": str(ctx.rate),
                                        "base_pensao_total": str(total) if len(items) > 1 else None}
    for s in slips:
        s.add(rub, s.contrib + s.rra_contrib)


def _split(value: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Rateio proporcional com a diferença de arredondamento no maior peso."""
    total = sum(weights, ZERO)
    if total <= 0 or value == 0:
        return [ZERO] * len(weights)
    shares = [q(value * w / total) for w in weights]
    diff = value - sum(shares, ZERO)
    if diff:
        i = max(range(len(weights)), key=lambda k: weights[k])
        shares[i] += diff
    return shares


def _person_flags(ctx: Context, person):
    from apps.people.models import Dependency

    deps = (Dependency.objects.filter(holder=person, tax_dependent=True, start_date__lte=ctx.m1)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=ctx.m0)).count())
    over_65 = add_years(person.birth_date, 65) <= ctx.m1
    molestia = (IrExemption.objects.filter(person=person, active=True, start__lte=ctx.m1)
                .filter(Q(end__isnull=True) | Q(end__gte=ctx.m0)).exists())
    return deps, over_65, molestia


def _alimony(ctx: Context, slip: Slip, ir_share: Decimal, calc: str, base_value: Decimal):
    """Pensões alimentícias do benefício. Base LIQUIDO = bruto − contribuição − IRRF."""
    total = ZERO
    rows = []
    for e, r in _entries(ctx, slip.benefit, {"PENSAO_ALIMENTICIA"}):
        if calc == "PENSAO_ALIMENTICIA_13" and (not e.on_13 or e.percent is None):
            continue
        if e.percent is not None:
            base = base_value if e.base != "LIQUIDO" else max(ZERO, base_value - slip.contrib - ir_share)
            value = q(base * e.percent / 100)
        else:
            value = q(e.amount)
        rows.append((e, value))
        total += value
    return total, rows


def _person_ir(ctx: Context, slips: list[Slip], decimo: bool = False):
    """IRRF do beneficiário (soma dos benefícios), com pensão alimentícia (iterativo quando base líquida)."""
    person = slips[0].benefit.beneficiary
    deps, over_65, molestia = _person_flags(ctx, person)
    calc_alim = "PENSAO_ALIMENTICIA_13" if decimo else "PENSAO_ALIMENTICIA"
    taxable = sum((s.taxable for s in slips), ZERO)
    pension_income = sum((s.pension_income for s in slips), ZERO)
    contrib = sum((s.contrib for s in slips), ZERO)
    ir_shares = [ZERO] * len(slips)
    alim = [(ZERO, []) for _ in slips]
    result = None
    for _ in range(30):
        alim = [_alimony(ctx, s, ir_shares[i], calc_alim, s.benefit_value) for i, s in enumerate(slips)]
        alimony = sum((a for a, _ in alim), ZERO)
        result = compute_ir(ctx.ir, taxable=taxable, pension_income=pension_income, contribution=contrib,
                            dependents=deps, alimony=alimony, over_65=over_65, molestia=molestia, decimo=decimo)
        new_shares = _split(result.tax, [s.taxable for s in slips])
        if new_shares == ir_shares:
            break
        ir_shares = new_shares

    ir_rub = ctx.rubrics.calc("IRRF_13" if decimo else "IRRF")
    alim_rub = ctx.rubrics.calc(calc_alim)
    for i, s in enumerate(slips):
        total_alim, rows = alim[i]
        for e, value in rows:
            name = f"{alim_rub.name} — {e.alimony_beneficiary.name}" if e.alimony_beneficiary_id else ""
            s.add(alim_rub, value, reference=f"{e.percent}%" if e.percent is not None else "", source_entry=e, name=name)
        s.add(ir_rub, ir_shares[i], reference=f"{result.rate * 100:.1f}%" if result.rate else "")
        key = "irrf_13" if decimo else "irrf"
        s.memory[key] = {**result.as_dict(), "dependentes": deps, "maior_65": over_65,
                         "rateio": str(ir_shares[i]), "rendimento_tributavel_total": str(taxable),
                         "pensao_alimenticia": str(total_alim)}
        s.memory["tributavel" if not decimo else "decimo_tributavel"] = str(s.taxable)
        if result.exempt_65:
            s.memory["isento_65" if not decimo else "decimo_isento_65"] = str(_split(result.exempt_65, [x.taxable for x in slips])[i])
        if molestia:
            s.memory["isento_molestia" if not decimo else "decimo_isento_molestia"] = str(s.taxable)
    return deps, molestia


def _rra(ctx: Context, s: Slip, deps: int, molestia: bool):
    if not s.rra_income:
        return
    if molestia:
        tax = ZERO
    else:
        base = max(ZERO, s.rra_income - s.rra_contrib - ctx.ir.dependent * deps)
        tax, _ = ctx.ir.tax(base, months=s.rra_months)
    s.add(ctx.rubrics.calc("IRRF_RRA"), tax, reference=f"{s.rra_months} meses")
    s.memory["rra"] = {"rendimento": str(s.rra_income), "contribuicao": str(s.rra_contrib), "meses": s.rra_months,
                       "irrf": str(tax)}


def _consignments(ctx: Context, s: Slip):
    compulsory = s.total(RubricKind.DESCONTO)
    margin = q(max(ZERO, s.margin_base - compulsory) * ctx.margin)
    used = ZERO
    for e, r in _entries(ctx, s.benefit, {"CONSIGNACAO"}):
        value = q(e.amount if e.amount is not None else s.margin_base * e.percent / 100)
        if used + value > margin:
            s.warnings.append(f"Consignação {r.code} ({e.consignee or e.contract or 'sem consignatária'}) de "
                              f"R$ {value} não descontada: margem consignável insuficiente (disponível R$ {margin - used}).")
            continue
        used += value
        s.add(r, value, reference=_installment_ref(e), source_entry=e,
              name=f"{r.name} — {e.consignee}" if e.consignee_id else "")
    s.memory["margem"] = {"base": str(s.margin_base), "percentual": str(ctx.margin), "margem": str(margin),
                          "utilizada": str(used)}


def calculate_monthly(ctx: Context) -> list[Slip]:
    slips = [_monthly_base(ctx, b) for b in benefits_for(ctx)]
    slips = [s for s in slips if s.lines]
    _contributions(ctx, slips)
    by_person: dict = defaultdict(list)
    for s in slips:
        by_person[s.benefit.beneficiary_id].append(s)
    for items in by_person.values():
        deps, molestia = _person_ir(ctx, items)
        for s in items:
            _rra(ctx, s, deps, molestia)
    for s in slips:
        _consignments(ctx, s)
    return slips


# ------------------------------------------------------------------ 13º
def avos(b, year: int) -> int:
    n = 0
    for m in range(1, 13):
        m0, m1 = month_bounds(year, m)
        start = max(b.start_date, m0)
        end = min(b.end_date, m1) if b.end_date else m1
        if start <= end and (end - start).days + 1 >= 15:
            n += 1
    return n


def calculate_decimo(ctx: Context) -> list[Slip]:
    rub = ctx.rubrics.calc("DECIMO")
    year = ctx.m0.year
    slips, ceased = [], []
    for b in benefits_for(ctx):
        if b.end_date is not None and b.end_date < ctx.m0:
            ceased.append(b)
            continue
        n = avos(b, year)
        if n == 0:
            continue
        value = q(b.amount * n / 12)
        s = Slip(benefit=b, benefit_value=value)
        s.add(rub, value, reference=f"{n}/12 avos")
        s.memory["avos"] = n
        if rub.inc_ir:
            s.taxable = value
            s.pension_income = value
        if rub.inc_rpps:
            s.rpps_base = value
        slips.append(s)
    if ceased:
        ctx.warnings.append(f"{len(ceased)} benefício(s) cessado(s) no ano sem 13º nesta folha (pagar o proporcional "
                            "na cessação, como diferença): " + ", ".join(b.beneficiary.name for b in ceased[:10]))
    _contributions(ctx, slips, decimo=True)
    by_person: dict = defaultdict(list)
    for s in slips:
        by_person[s.benefit.beneficiary_id].append(s)
    for items in by_person.values():
        _person_ir(ctx, items, decimo=True)
    return slips
