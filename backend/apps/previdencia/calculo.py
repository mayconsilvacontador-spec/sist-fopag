"""
Cálculo da média e dos proventos (simulação e concessão).

Média — Lei 10.887/2004, art. 1º, e Lei Municipal 3.965/2011, art. 62:
- salários de contribuição desde 07/1994 (RPPS + RGPS, somados por mês) até a DATA-BASE do cálculo
  (concessão: abertura do processo; simulação: data da simulação);
- limites mês a mês (art. 62, § 6º): não inferior ao salário mínimo da competência (parâmetro `salario_minimo`)
  e, nos meses de RGPS, não superior ao teto do RGPS da competência (parâmetro `rgps.teto`);
- atualização mês a mês pela tabela de fatores do mês da data-base (art. 62, § 2º);
- maiores remunerações definidas após atualização e limites (§ 7º); nº de competências dos 80% sem decimais (§ 8º);
- competência sem contribuição dentro do vínculo com o RPPS deve usar a remuneração do cargo (§ 3º): o sistema
  NÃO inventa valor — aponta a lacuna como pendência.
Média 80%: 80% maiores (regras anteriores à reforma). Média 100%: todas (EC 103, art. 26).

`pendencias` impedem a concessão (o cálculo é recusado); na simulação aparecem como avisos.
Proventos: limitados à remuneração do cargo efetivo (art. 62, § 10) ANTES da proporcionalidade (art. 63, § 1º) e
nunca inferiores ao salário mínimo (CF, art. 40, § 2º).
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .models import ContributionRegime, ContributionSalary, CorrectionFactor
from .tempo import DAYS_YEAR

CENT = Decimal("0.01")
START = date(1994, 7, 1)
EC41_REDUTOR_35_ATE = date(2005, 12, 31)  # EC 41, art. 2º, § 1º: 3,5% até 31/12/2005; 5% a partir de 01/01/2006


def _q(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def _month(d: date) -> date:
    return d.replace(day=1)


def _next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def _fmt_months(months: list[date], limit: int = 12) -> str:
    shown = ", ".join(f"{m:%m/%Y}" for m in months[:limit])
    return shown + (f" e mais {len(months) - limit}" if len(months) > limit else "")


class Series:
    """Parâmetro versionado carregado uma vez (valor vigente em cada data, sem nova consulta)."""

    def __init__(self, institution, key: str):
        from apps.institutions.models import Parameter

        rows = (Parameter.objects.filter(institution=institution, key=key)
                .order_by("valid_from", "version").values_list("valid_from", "valid_to", "value"))
        self.rows = [(vf, vt, Decimal(str(v))) for vf, vt, v in rows]
        self.starts = [r[0] for r in self.rows]

    def at(self, on: date) -> Decimal | None:
        i = bisect_right(self.starts, on) - 1
        while i >= 0:
            vf, vt, v = self.rows[i]
            if vt is None or vt >= on:
                return v
            i -= 1
        return None


def rpps_months(pt, until: date) -> set[date]:
    """Competências (desde 07/1994) em que o servidor estava vinculado ao RPPS do ente, sem afastamento não computável."""
    from .models import TimeNature

    months: set[date] = set()
    for p in pt.periods:
        if p.nature != TimeNature.RPPS_ORIGEM:
            continue
        m = _month(max(p.start, START))
        end = min(p.end or until, until)
        while m <= end:
            m_end = _next_month(m) - timedelta(days=1)
            off = any(s <= m and (e or until) >= m_end for s, e, _ in p.deductions)
            if not off:
                months.add(m)
            m = _next_month(m)
    return months


class Averages:
    """
    Médias até a data-base `on`. `pt` (PersonTime) permite apontar lacunas no vínculo com o RPPS.
    `warnings` = avisos; `pendencias` = impedimentos para concessão; `memoria` = explicação do cálculo.
    """

    def __init__(self, person, on: date, pt=None):
        self.on = on
        self.warnings: list[str] = []
        self.pendencias: list[str] = []
        inst = person.institution
        monthly = defaultdict(Decimal)
        rgps = set()
        rpps_last = rpps_last_comp = None
        for s in ContributionSalary.objects.filter(person=person, competence__gte=START, competence__lte=on) \
                .order_by("competence"):
            comp = _month(s.competence)
            monthly[comp] += s.amount
            if s.regime == ContributionRegime.RPPS:
                rpps_last, rpps_last_comp = s.amount, comp
            else:
                rgps.add(comp)
        self.months = len(monthly)
        self.last_rpps, self.last_rpps_comp = rpps_last, rpps_last_comp

        # ---- limites mês a mês (art. 62, § 6º) sobre o valor da competência
        sm, teto = Series(inst, "salario_minimo"), Series(inst, "rgps.teto")
        no_sm, no_teto, raised, capped = [], [], 0, 0
        limited = {}
        for comp, value in monthly.items():
            floor = sm.at(comp)
            if floor is None:
                no_sm.append(comp)
            elif value < floor:
                value, raised = floor, raised + 1
            if comp in rgps:
                cap = teto.at(comp)
                if cap is None:
                    no_teto.append(comp)
                elif value > cap:
                    value, capped = cap, capped + 1
            limited[comp] = value
        if no_sm:
            self.pendencias.append(f"Salário mínimo não cadastrado (Parâmetros › salario_minimo) para: "
                                   f"{_fmt_months(sorted(no_sm))} — o piso do art. 62, § 6º, I, não pôde ser aplicado.")
        if no_teto:
            self.pendencias.append(f"Teto do RGPS não cadastrado (Parâmetros › rgps.teto) para competência(s) de RGPS: "
                                   f"{_fmt_months(sorted(no_teto))} — art. 62, § 6º, II.")

        # ---- atualização (art. 62, § 2º)
        table = (CorrectionFactor.objects.filter(institution=inst, table_month__lte=on)
                 .order_by("-table_month").values_list("table_month", flat=True).first())
        self.table_month = table
        factors = {}
        if table:
            factors = {_month(k): v for k, v in CorrectionFactor.objects.filter(institution=inst, table_month=table)
                       .values_list("competence", "factor")}
        corrected, missing = [], []
        for comp, value in limited.items():
            f = factors.get(comp)
            if f is None:
                missing.append(comp)
                f = Decimal(1)
            corrected.append(value * f)

        if not monthly:
            self.warnings.append("Sem salários de contribuição cadastrados — média não calculada.")
        elif not table:
            self.pendencias.append("Sem tabela de fatores de atualização (Histórico contributivo › Tabelas de "
                                   "atualização): a média não pode ser calculada com valores nominais "
                                   "(regra da média: valores atualizados mês a mês).")
        else:
            if missing:
                self.pendencias.append(f"{len(missing)} competência(s) sem fator na tabela de {table:%m/%Y}: "
                                       f"{_fmt_months(sorted(missing))}.")
            if _month(table) < _month(on):
                self.warnings.append(f"Tabela de fatores usada: {table:%m/%Y} (a data-base é {on:%m/%Y}) — confira se "
                                     "a tabela do mês já foi publicada.")

        # ---- lacunas no vínculo com o RPPS (art. 62, § 3º)
        self.gaps: list[date] = []
        if pt is not None and monthly:
            expected = {m for m in rpps_months(pt, on) if m < _month(on)}
            self.gaps = sorted(expected - set(monthly))
            if self.gaps:
                self.pendencias.append(
                    f"{len(self.gaps)} competência(s) do vínculo com o RPPS sem salário de contribuição: "
                    f"{_fmt_months(self.gaps)}. Cadastre a remuneração do cargo nesses meses (legislação do RPPS) ou registre o afastamento não computável no histórico funcional.")

        corrected.sort(reverse=True)
        self.media100 = _q(sum(corrected) / len(corrected)) if corrected else None
        n80 = max(1, int(len(corrected) * Decimal("0.8"))) if corrected else 0  # decimais desprezados (§ 8º)
        top = corrected[:n80]
        self.media80 = _q(sum(top) / len(top)) if top else None
        self.memoria = {
            "data_base": on.isoformat(), "competencias": self.months, "competencias_80": n80,
            "tabela_fatores": table.strftime("%m/%Y") if table else "",
            "elevadas_ao_salario_minimo": raised, "limitadas_ao_teto_rgps": capped,
        }


def salario_minimo(institution, on: date) -> Decimal | None:
    return Series(institution, "salario_minimo").at(on)


def estimate(rule, evaluator, avg: Averages, on: date, eligible: date | None = None,
             remuneration: Decimal | None = None) -> dict:
    """
    Valor dos proventos pela regra, com média e tempo apurados na data-base `on`.
    `eligible` = data em que os requisitos da regra foram cumpridos (define redutor da EC 41 e o regime da
    compulsória). `remuneration` = remuneração do cargo efetivo (padrão: última remuneração de contribuição).
    """
    from apps.institutions.services import get_parameter

    from .rules import age_years

    person = evaluator.person
    eligible = eligible or on
    link = evaluator.pt.link
    if remuneration is None:
        remuneration = avg.last_rpps or (link.base_salary if link and link.base_salary else None)
    warnings: list[str] = []
    code = rule.code
    sex_f = person.sex == 1
    days = evaluator.summary(on).contribuicao
    whole_years = Decimal(days // DAYS_YEAR)

    def perc_103():
        return min(Decimal(100), Decimal(60) + Decimal(2) * max(Decimal(0), whole_years - 20))

    def cap(v):
        """Limite à remuneração do cargo efetivo (art. 40, § 2º, CF) — antes de qualquer fração."""
        if v is not None and remuneration and v > remuneration:
            return remuneration, " — limitada à remuneração do cargo efetivo"
        return v, ""

    value, how, fraction = None, "", None
    ps_start = evaluator.pt.public_service_start
    early = ps_start is not None and ps_start <= date(2003, 12, 31)

    if code in ("EC41_ART6", "EC41_ART6_PROF", "EC47_ART3"):
        value, how = remuneration, "Integralidade (remuneração do cargo efetivo)"
    elif code in ("EC103_ART20", "EC103_ART20_PROF"):
        if early:
            value, how = remuneration, "Integralidade (ingresso até 31/12/2003)"
        elif avg.media100:
            value, how = cap(avg.media100)
            how = "100% da média" + how
    elif code in ("EC103_ART4", "EC103_ART4_PROF"):
        age_int = (62 if code == "EC103_ART4" else 57) if sex_f else (65 if code == "EC103_ART4" else 60)
        if early and age_years(person.birth_date, on) >= age_int:
            value, how = remuneration, f"Integralidade (ingresso até 2003 e {age_int} anos)"
        elif avg.media100:
            pct = perc_103()
            value, how = cap(_q(avg.media100 * pct / 100))
            how = f"{pct}% da média (60% + 2% por ano acima de 20)" + how
    elif code.startswith("EC103_ART10") or code == "EC103_ART21":
        if avg.media100:
            pct = perc_103()
            value, how = cap(_q(avg.media100 * pct / 100))
            how = f"{pct}% da média (60% + 2% por ano acima de 20)" + how
    elif code in ("CF40_IIIA", "CF40_IIIA_PROF"):
        if avg.media80:
            value, how = cap(avg.media80)
            how = "Média dos 80% maiores salários" + how
    elif code == "CF40_IIIB" and avg.media80:
        base, note = cap(avg.media80)
        required = (30 if sex_f else 35) * DAYS_YEAR
        fraction = min(Decimal(1), Decimal(days) / Decimal(required)).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        value = _q(base * fraction)
        how = (f"Proporcional: {days} ÷ {required} dias = {fraction} × média dos 80% maiores{note} "
               "(CF, art. 40, § 1º, III, b)")
    elif code == "EC41_ART2" and avg.media80:
        base, note = cap(avg.media80)
        ref_age = 55 if sex_f else 60
        anticip = max(0, ref_age - age_years(person.birth_date, eligible))
        per_year = Decimal("3.5") if eligible <= EC41_REDUTOR_35_ATE else Decimal(5)
        red = per_year * anticip
        value = _q(base * (100 - red) / 100)
        how = f"Média dos 80% maiores{note} com redutor de {red}% ({per_year}% × {anticip} ano(s) — EC 41, art. 2º, § 1º)"
    elif code == "COMPULSORIA":
        reform = get_parameter(person.institution, "previdencia.vigencia_reforma_local")
        reform = date.fromisoformat(reform) if reform else None
        if (reform is None or eligible < reform) and avg.media80:  # sem reforma local: regra antiga
            if reform is None:
                warnings.append("RPPS sem data de reforma local cadastrada: compulsória calculada pela regra anterior à EC 103.")
            base, note = cap(avg.media80)
            required = (30 if sex_f else 35) * DAYS_YEAR
            fraction = min(Decimal(1), Decimal(days) / Decimal(required)).quantize(Decimal("0.0001"), ROUND_HALF_UP)
            value = _q(base * fraction)
            how = (f"Compulsória (antes da reforma): {days} ÷ {required} dias = {fraction} × média dos 80% maiores"
                   f"{note} (CF, art. 40, § 1º, II)")
        elif reform is not None and eligible >= reform and avg.media100:
            pct = perc_103()
            base, note = cap(_q(avg.media100 * pct / 100))
            fraction = min(Decimal(1), Decimal(days) / Decimal(20 * DAYS_YEAR)).quantize(Decimal("0.0001"), ROUND_HALF_UP)
            value = _q(base * fraction)
            how = (f"Compulsória (EC 103, art. 26, § 4º): {pct}% da média{note} × {days} ÷ {20 * DAYS_YEAR} dias "
                   f"(limitado a 1) = {fraction}")
    else:
        warnings.append("Forma de cálculo não estimada automaticamente para esta regra.")

    floor = salario_minimo(person.institution, on)
    if value is not None and floor and value < floor:
        value, how = floor, how + " — elevada ao salário mínimo (CF, art. 40, § 2º)"
    if value is None and not warnings:
        warnings.append("Dados insuficientes para estimar.")
    return {"valor": str(value) if value is not None else None, "forma": how, "avisos": warnings,
            "fracao": str(fraction) if fraction is not None else None}
