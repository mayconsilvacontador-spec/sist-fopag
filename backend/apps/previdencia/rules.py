"""
Motor de regras de aposentadoria (simulação e elegibilidade).

Cada RetirementRule guarda em `params` os requisitos; este motor os interpreta:

    idade            {"F": 62, "M": 65}           idade mínima (anos completos)
    idade_desde      [{"desde": "2022-01-01", "F": 57, "M": 62}]   idade que muda com o tempo
    contribuicao     {"F": 25, "M": 25}           anos de contribuição
    contribuicao_tipo  "total" | "magisterio" | "especial"
    servico_publico  10   carreira 0   cargo 5     anos
    pontos           {"F": 86, "M": 96, "ano_base": 2019, "max_F": 100, "max_M": 105}
                     (+1 ponto por ano a partir do ano seguinte ao ano_base)
    pedagio          {"percentual": 100, "referencia": "2025-06-15"}  tempo adicional sobre o que faltava
    reducao_ec47     true   idade mínima reduzida 1 ano por ano de contribuição excedente
    ingresso_servico_publico_ate  "2003-12-31"
    ingresso_ente_antes_de        "2025-06-15"

Sexo no Cadastro Único (SPREV): 1 = feminino (F), 2 = masculino (M).
"""
from django.utils import timezone
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .tempo import DAYS_YEAR, PersonTime

SCAN_STEP = 30
MAX_AGE = 75


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29/02
        return d.replace(year=d.year + years, day=28)


def age_years(birth: date, on: date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


@dataclass
class Requirement:
    key: str
    label: str
    required: str
    achieved: str
    met: bool
    date_met: date | None = None


@dataclass
class RuleResult:
    rule: object
    applies: bool
    status: str  # CUMPRIDA | CUMPRIRA | NAO_ALCANCAVEL | NAO_SE_APLICA
    eligible_date: date | None
    requirements: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    reference_date: date | None = None  # data em que os requisitos exibidos foram apurados


class RuleEvaluator:
    def __init__(self, person, pt: PersonTime | None = None, today: date | None = None):
        self.person = person
        self.pt = pt or PersonTime(person)
        self.today = today or timezone.localdate()
        self.sx = "F" if person.sex == 1 else "M"
        self._cache: dict[date, object] = {}

    def summary(self, on: date):
        s = self._cache.get(on)
        if s is None:
            s = self._cache[on] = self.pt.summary(on)
        return s

    # ---------------------------------------------------------------- requisitos numéricos
    def _req_age(self, p, on: date, contrib_days: int) -> int | None:
        if "idade" not in p:
            return None
        age = p["idade"][self.sx]
        for step in p.get("idade_desde", []):
            if on >= _d(step["desde"]):
                age = step[self.sx]
        if p.get("reducao_ec47") and "contribuicao" in p:
            excess = (contrib_days - p["contribuicao"][self.sx] * DAYS_YEAR) // DAYS_YEAR
            age -= max(0, excess)
        return age

    def _req_points(self, p, on: date) -> int | None:
        pts = p.get("pontos")
        if not pts:
            return None
        inc = max(0, on.year - pts.get("ano_base", on.year))
        return min(pts[self.sx] + inc, pts.get(f"max_{self.sx}", 999))

    def _req_contrib_days(self, p) -> int | None:
        if "contribuicao" not in p:
            return None
        base = p["contribuicao"][self.sx] * DAYS_YEAR
        ped = p.get("pedagio")
        if ped:
            ref = _d(ped["referencia"])
            had = self._contrib_of_type(p, self.summary(ref))
            missing = max(0, base - had)
            base += int(Decimal(missing) * Decimal(ped["percentual"]) / 100)
        return base

    @staticmethod
    def _contrib_of_type(p, s) -> int:
        kind = p.get("contribuicao_tipo", "total")
        return s.magisterio if kind == "magisterio" else s.especial if kind == "especial" else s.contribuicao

    def check(self, rule, on: date) -> tuple[bool, list[Requirement]]:
        p, s = rule.params, self.summary(on)
        reqs: list[Requirement] = []
        contrib = self._contrib_of_type(p, s)
        birth = self.person.birth_date

        age_req = self._req_age(p, on, s.contribuicao)
        if age_req is not None:
            have = age_years(birth, on)
            label = "Idade mínima" + (" (reduzida pelo tempo excedente — EC 47)" if p.get("reducao_ec47") else "")
            reqs.append(Requirement("idade", label, f"{age_req} anos", f"{have} anos", have >= age_req))
        c_req = self._req_contrib_days(p)
        if c_req is not None:
            kind = p.get("contribuicao_tipo", "total")
            label = {"total": "Tempo de contribuição", "magisterio": "Tempo de efetivo exercício no magistério",
                     "especial": "Tempo de efetiva exposição a agentes nocivos"}[kind]
            if p.get("pedagio"):
                label += f" (com pedágio de {p['pedagio']['percentual']}%)"
            reqs.append(Requirement("contribuicao", label, _fmt_days(c_req), _fmt_days(contrib), contrib >= c_req))
        for key, label, have in (("servico_publico", "Tempo de serviço público", s.servico_publico),
                                 ("carreira", "Tempo na carreira", s.carreira), ("cargo", "Tempo no cargo", s.cargo)):
            if p.get(key):
                need = p[key] * DAYS_YEAR
                reqs.append(Requirement(key, label, f"{p[key]} anos", _fmt_days(have), have >= need))
        pts_req = self._req_points(p, on)
        if pts_req is not None:
            pts = (Decimal((on - birth).days) + Decimal(s.contribuicao)) / DAYS_YEAR
            pts = pts.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            reqs.append(Requirement("pontos", "Pontuação (idade + tempo de contribuição)", f"{pts_req} pontos",
                                    f"{pts} pontos", pts >= pts_req))
        return all(r.met for r in reqs), reqs

    # ---------------------------------------------------------------- avaliação
    def _entry_ok(self, rule) -> tuple[bool, str]:
        p = rule.params
        if p.get("ingresso_servico_publico_ate"):
            limit = _d(p["ingresso_servico_publico_ate"])
            start = self.pt.public_service_start
            if start is None or start > limit:
                return False, f"Exige ingresso no serviço público até {limit:%d/%m/%Y}."
        if p.get("ingresso_ente_antes_de"):
            limit = _d(p["ingresso_ente_antes_de"])
            start = self.pt.municipal_effective_start
            if start is None or start >= limit:
                return False, f"Exige ingresso em cargo efetivo no ente antes de {limit:%d/%m/%Y}."
        return True, ""

    def evaluate(self, rule) -> RuleResult:
        ok, why = self._entry_ok(rule)
        if not ok:
            return RuleResult(rule, False, "NAO_SE_APLICA", None, notes=[why])

        birth = self.person.birth_date
        first = min((pp.start for pp in self.pt.periods), default=self.today)
        start = max(rule.valid_from or first, first, _add_years(birth, 16))
        # Sem vínculo ativo o tempo deixa de crescer (os períodos têm fim); a idade continua contando
        end = min(rule.valid_to or _add_years(birth, MAX_AGE), _add_years(birth, MAX_AGE))

        eligible = None
        if start <= end:
            d = start
            prev = None
            while d <= end:
                met, _ = self.check(rule, d)
                if met:
                    lo = prev or start
                    for i in range((d - lo).days + 1):  # refina dia a dia
                        dd = lo + timedelta(days=i)
                        if self.check(rule, dd)[0]:
                            eligible = dd
                            break
                    break
                prev = d + timedelta(days=1)
                d += timedelta(days=SCAN_STEP)
            if eligible is None and end >= start and self.check(rule, end)[0]:
                eligible = end

        ref = min(self.today, rule.valid_to) if rule.valid_to else self.today
        _, reqs = self.check(rule, ref)
        if eligible:
            for r in reqs:
                r.date_met = eligible if not r.met else None
        if eligible is None:
            status = "NAO_ALCANCAVEL"
            notes = ["Os requisitos não foram cumpridos até " + f"{rule.valid_to:%d/%m/%Y}." if rule.valid_to
                     else "Os requisitos não serão cumpridos até a idade-limite (75 anos)."]
        else:
            status = "CUMPRIDA" if eligible <= self.today else "CUMPRIRA"
            notes = []
        return RuleResult(rule, True, status, eligible, reqs, notes, reference_date=ref)


def _fmt_days(days: int) -> str:
    """Ano de 365 dias; o resto fica em dias (evita '12 meses' da conversão por meses de 30 dias)."""
    days = max(days, 0)
    y, rest = divmod(days, DAYS_YEAR)
    total = f"{days:,}".replace(",", ".")
    return f"{y} anos e {rest} dias ({total} dias)" if rest else f"{y} anos ({total} dias)"


# ---------------------------------------------------------------- regras de Barra Mansa (EC 103 + Emenda 28/2025)
def default_rules(reform: date) -> list[dict]:
    """
    Regras do RPPS após a Emenda à Lei Orgânica nº 28/2025 (vigente a partir da LC 106/2025).
    `reform` = início da vigência local da reforma. Requisitos das regras antigas
    precisam ter sido cumpridos até o dia anterior (direito adquirido — art. 5º).
    """
    cut = reform - timedelta(days=1)
    R = reform.isoformat()
    media80 = "Média dos 80% maiores salários de contribuição desde 07/1994 (Lei 10.887/2004); reajuste pelo RGPS"
    media103 = "60% da média de 100% dos salários de contribuição + 2% por ano que exceder 20 anos (EC 103, art. 26)"
    integral = "Integralidade (última remuneração no cargo efetivo)"
    paridade = "Paridade com os servidores ativos"
    return [
        # ---------------- direito adquirido (requisitos até a véspera da reforma local)
        dict(code="CF40_IIIA", name="Voluntária por idade e tempo de contribuição", group="DIREITO_ADQUIRIDO",
             legal_basis="Art. 40, § 1º, III, 'a', CF (redação da EC 41/2003)", engine="REQUISITOS",
             params={"idade": {"F": 55, "M": 60}, "contribuicao": {"F": 30, "M": 35}, "servico_publico": 10, "cargo": 5},
             valid_to=cut, proventos=media80, paridade="Sem paridade"),
        dict(code="CF40_IIIA_PROF", name="Voluntária do professor", group="DIREITO_ADQUIRIDO", for_teacher=True,
             legal_basis="Art. 40, § 1º, III, 'a', e § 5º, CF (EC 41/2003)", engine="REQUISITOS",
             params={"idade": {"F": 50, "M": 55}, "contribuicao": {"F": 25, "M": 30},
                     "contribuicao_tipo": "magisterio", "servico_publico": 10, "cargo": 5},
             valid_to=cut, proventos=media80, paridade="Sem paridade"),
        dict(code="CF40_IIIB", name="Voluntária por idade (proventos proporcionais)", group="DIREITO_ADQUIRIDO",
             legal_basis="Art. 40, § 1º, III, 'b', CF (EC 41/2003)", engine="REQUISITOS",
             params={"idade": {"F": 60, "M": 65}, "servico_publico": 10, "cargo": 5},
             valid_to=cut, proventos="Proporcionais ao tempo de contribuição, sobre a média dos 80% maiores salários",
             paridade="Sem paridade"),
        dict(code="EC41_ART2", name="Transição do art. 2º da EC 41 (com redutor)", group="DIREITO_ADQUIRIDO",
             legal_basis="Art. 2º da EC 41/2003", engine="REQUISITOS",
             params={"idade": {"F": 48, "M": 53}, "contribuicao": {"F": 30, "M": 35}, "cargo": 5,
                     "pedagio": {"percentual": 20, "referencia": "1998-12-16"},
                     "ingresso_servico_publico_ate": "1998-12-16"},
             valid_to=cut, proventos=media80 + ", com redutor de 5% por ano antecipado em relação a 60 (H) / 55 (M)",
             paridade="Sem paridade",
             notes="O bônus de tempo do professor (art. 2º, § 4º) não é aplicado automaticamente — conferir."),
        dict(code="EC41_ART6", name="Transição do art. 6º da EC 41 (integralidade)", group="DIREITO_ADQUIRIDO",
             legal_basis="Art. 6º da EC 41/2003", engine="REQUISITOS",
             params={"idade": {"F": 55, "M": 60}, "contribuicao": {"F": 30, "M": 35}, "servico_publico": 20,
                     "carreira": 10, "cargo": 5, "ingresso_servico_publico_ate": "2003-12-31"},
             valid_to=cut, proventos=integral, paridade=paridade),
        dict(code="EC41_ART6_PROF", name="Transição do art. 6º da EC 41 — professor", group="DIREITO_ADQUIRIDO",
             for_teacher=True, legal_basis="Art. 6º da EC 41/2003 c/c art. 40, § 5º, CF", engine="REQUISITOS",
             params={"idade": {"F": 50, "M": 55}, "contribuicao": {"F": 25, "M": 30},
                     "contribuicao_tipo": "magisterio", "servico_publico": 20, "carreira": 10, "cargo": 5,
                     "ingresso_servico_publico_ate": "2003-12-31"},
             valid_to=cut, proventos=integral, paridade=paridade),
        dict(code="EC47_ART3", name="Transição do art. 3º da EC 47 (idade reduzida)", group="DIREITO_ADQUIRIDO",
             legal_basis="Art. 3º da EC 47/2005", engine="REQUISITOS",
             params={"idade": {"F": 55, "M": 60}, "reducao_ec47": True, "contribuicao": {"F": 30, "M": 35},
                     "servico_publico": 25, "carreira": 15, "cargo": 5, "ingresso_servico_publico_ate": "1998-12-16"},
             valid_to=cut, proventos=integral, paridade=paridade + " (estendida às pensões)"),
        # ---------------- transições da EC 103 (Emenda 28, art. 4º)
        dict(code="EC103_ART4", name="Transição por pontos", group="TRANSICAO",
             legal_basis="Art. 4º da EC 103/2019 (Emenda à LOM 28/2025, art. 4º, I)", engine="REQUISITOS",
             params={"idade": {"F": 56, "M": 61}, "idade_desde": [{"desde": "2022-01-01", "F": 57, "M": 62}],
                     "contribuicao": {"F": 30, "M": 35}, "servico_publico": 20, "cargo": 5,
                     "pontos": {"F": 86, "M": 96, "ano_base": 2019, "max_F": 100, "max_M": 105},
                     "ingresso_ente_antes_de": R},
             valid_from=reform,
             proventos=f"{integral} se ingressou no serviço público até 31/12/2003 e tiver 62 (M) / 65 (H) anos; "
                       f"senão, {media103}",
             paridade="Paridade apenas na hipótese de integralidade"),
        dict(code="EC103_ART4_PROF", name="Transição por pontos — professor", group="TRANSICAO", for_teacher=True,
             legal_basis="Art. 4º, §§ 4º e 5º, da EC 103/2019 (Emenda à LOM 28/2025)", engine="REQUISITOS",
             params={"idade": {"F": 51, "M": 56}, "idade_desde": [{"desde": "2022-01-01", "F": 52, "M": 57}],
                     "contribuicao": {"F": 25, "M": 30}, "contribuicao_tipo": "magisterio", "servico_publico": 20,
                     "cargo": 5, "pontos": {"F": 81, "M": 91, "ano_base": 2019, "max_F": 92, "max_M": 100},
                     "ingresso_ente_antes_de": R},
             valid_from=reform,
             proventos=f"{integral} se ingressou até 31/12/2003 e tiver 57 (M) / 60 (H) anos; senão, {media103}",
             paridade="Paridade apenas na hipótese de integralidade"),
        dict(code="EC103_ART20", name="Transição com pedágio de 100%", group="TRANSICAO",
             legal_basis="Art. 20 da EC 103/2019 (Emenda à LOM 28/2025, art. 4º, II)", engine="REQUISITOS",
             params={"idade": {"F": 57, "M": 60}, "contribuicao": {"F": 30, "M": 35}, "servico_publico": 20,
                     "cargo": 5, "pedagio": {"percentual": 100, "referencia": R}, "ingresso_ente_antes_de": R},
             valid_from=reform,
             proventos=f"{integral} se ingressou no serviço público até 31/12/2003; senão, 100% da média",
             paridade="Paridade apenas na hipótese de integralidade",
             notes="Pedágio calculado sobre o tempo que faltava na data de vigência local da reforma — confirmar "
                   "o entendimento do órgão de controle."),
        dict(code="EC103_ART20_PROF", name="Transição com pedágio de 100% — professor", group="TRANSICAO",
             for_teacher=True, legal_basis="Art. 20, § 1º, da EC 103/2019 (Emenda à LOM 28/2025)", engine="REQUISITOS",
             params={"idade": {"F": 52, "M": 55}, "contribuicao": {"F": 25, "M": 30}, "contribuicao_tipo": "magisterio",
                     "servico_publico": 20, "cargo": 5, "pedagio": {"percentual": 100, "referencia": R},
                     "ingresso_ente_antes_de": R},
             valid_from=reform,
             proventos=f"{integral} se ingressou até 31/12/2003; senão, 100% da média",
             paridade="Paridade apenas na hipótese de integralidade"),
        dict(code="EC103_ART21", name="Transição da aposentadoria especial (agentes nocivos)", group="TRANSICAO",
             legal_basis="Art. 21 da EC 103/2019 (Emenda à LOM 28/2025, art. 4º, III)", engine="REQUISITOS",
             params={"contribuicao": {"F": 25, "M": 25}, "contribuicao_tipo": "especial", "servico_publico": 20,
                     "cargo": 5, "pontos": {"F": 86, "M": 86}, "ingresso_ente_antes_de": R},
             valid_from=reform, proventos=media103, paridade="Sem paridade"),
        # ---------------- regra permanente (Emenda 28, art. 2º)
        dict(code="EC103_ART10_I", name="Voluntária — regra permanente", group="PERMANENTE",
             legal_basis="Art. 10, § 1º, I, da EC 103/2019 (Emenda à LOM 28/2025, arts. 1º e 2º)", engine="REQUISITOS",
             params={"idade": {"F": 62, "M": 65}, "contribuicao": {"F": 25, "M": 25}, "servico_publico": 10, "cargo": 5},
             valid_from=reform, proventos=media103, paridade="Sem paridade (reajuste pelo RGPS)"),
        dict(code="EC103_ART10_PROF", name="Voluntária do professor — regra permanente", group="PERMANENTE",
             for_teacher=True, legal_basis="Art. 10, § 2º, III, da EC 103/2019 (Emenda à LOM 28/2025)",
             engine="REQUISITOS",
             params={"idade": {"F": 57, "M": 60}, "contribuicao": {"F": 25, "M": 25},
                     "contribuicao_tipo": "magisterio", "servico_publico": 10, "cargo": 5},
             valid_from=reform, proventos=media103, paridade="Sem paridade"),
        dict(code="EC103_ART10_ESPECIAL", name="Especial por agentes nocivos — regra permanente", group="PERMANENTE",
             legal_basis="Art. 10, § 2º, II, da EC 103/2019 (Emenda à LOM 28/2025)", engine="REQUISITOS",
             params={"idade": {"F": 60, "M": 60}, "contribuicao": {"F": 25, "M": 25}, "contribuicao_tipo": "especial",
                     "servico_publico": 10, "cargo": 5},
             valid_from=reform, proventos=media103, paridade="Sem paridade"),
        # ---------------- compulsória
        dict(code="COMPULSORIA", name="Compulsória", group="COMPULSORIA",
             legal_basis="Art. 40, § 1º, II, CF e LC 152/2015", engine="REQUISITOS", params={"idade": {"F": 75, "M": 75}},
             proventos="Proporcionais ao tempo de contribuição", paridade="Sem paridade",
             gives_permanence_bonus=False),
    ]


def seed_rules(institution, reform: date) -> int:
    from .models import RetirementRule

    created = 0
    for data in default_rules(reform):
        code = data["code"]
        data = {"for_teacher": False, "gives_permanence_bonus": True, "valid_from": None, "valid_to": None,
                "notes": "", **data}
        _, c = RetirementRule.objects.get_or_create(institution=institution, code=code, defaults=data)
        created += int(c)
    return created
