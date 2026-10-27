"""
IRRF e contribuição de aposentados e pensionistas.

Tabela do IRRF = parâmetro versionado 'irrf.tabela' (JSON):
  {"faixas": [["2428.80", "0", "0"], ["2826.65", "0.075", "182.16"], ..., [null, "0.275", "908.73"]],
   "deducao_dependente": "189.59", "desconto_simplificado": "607.20", "parcela_isenta_65": "1903.98",
   "reducao": {"limite_isencao": "5000.00", "reducao_maxima": "312.89", "limite_reducao": "7350.00",
               "constante": "978.62", "fator": "0.133145", "aplica_13": true} | null,
   "fonte": "..."}

Imposto mensal: o menor entre (a) deduções legais — contribuição previdenciária, dependentes e pensão
alimentícia — e (b) desconto simplificado mensal, que as substitui. Maiores de 65 anos: parcela isenta de
proventos de aposentadoria e pensão (Lei 7.713/1988, art. 6º, XV), inclusive no 13º. A redução da
Lei 15.270/2025 (a partir de 2026) é aplicada sobre o imposto calculado, conforme os rendimentos tributáveis.

Contribuição (Emenda à LOM 28/2025, art. 7º, parágrafo único; CF art. 40, § 18): alíquota sobre a parcela
dos proventos/pensão que supere o teto do RGPS.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.core.exceptions import BusinessRuleError

CENT = Decimal("0.01")
ZERO = Decimal("0")
IR_PARAM = "irrf.tabela"
RATE_PARAM = "folha.aliquota_segurado"
MARGIN_PARAM = "folha.margem_consignavel"


def q(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def D(v) -> Decimal:
    return Decimal(str(v)) if v is not None else ZERO


@dataclass
class IrTable:
    brackets: list  # [(limite | None, aliquota, deducao)]
    dependent: Decimal
    simplified: Decimal
    exempt_65: Decimal
    reduction: dict | None
    source: str

    @classmethod
    def load(cls, institution, on: date) -> "IrTable":
        from apps.institutions.services import get_parameter

        v = get_parameter(institution, IR_PARAM, on)
        if not v:
            raise BusinessRuleError(
                f"Tabela do IRRF vigente em {on:%m/%Y} não cadastrada (parâmetro '{IR_PARAM}'). "
                "Rode 'seed_payroll' ou cadastre em Administração › Parâmetros.")
        return cls(
            brackets=[(D(lim) if lim not in (None, "") else None, D(rate), D(ded)) for lim, rate, ded in v["faixas"]],
            dependent=D(v.get("deducao_dependente")), simplified=D(v.get("desconto_simplificado")),
            exempt_65=D(v.get("parcela_isenta_65")), reduction=v.get("reducao"), source=v.get("fonte", ""))

    def tax(self, base: Decimal, months: int = 1) -> tuple[Decimal, Decimal]:
        """Imposto pela tabela progressiva. months > 1 = RRA (faixas e parcelas multiplicadas pelo nº de meses)."""
        if base <= 0:
            return ZERO, ZERO
        for lim, rate, ded in self.brackets:
            if lim is None or base <= lim * months:
                return max(ZERO, q(base * rate - ded * months)), rate
        return ZERO, ZERO

    def reduce(self, tax: Decimal, taxable_income: Decimal, decimo: bool = False) -> Decimal:
        """Redução da Lei 15.270/2025 (nunca maior que o imposto)."""
        r = self.reduction
        if not r or tax <= 0 or (decimo and not r.get("aplica_13", True)):
            return ZERO
        if taxable_income <= D(r["limite_isencao"]):
            red = D(r["reducao_maxima"])
        elif taxable_income <= D(r["limite_reducao"]):
            red = q(D(r["constante"]) - D(r["fator"]) * taxable_income)
        else:
            red = ZERO
        return min(tax, max(ZERO, red))


@dataclass
class IrResult:
    base: Decimal
    tax: Decimal
    rate: Decimal
    method: str  # LEGAL | SIMPLIFICADO | ISENTO_MOLESTIA | ISENTO
    reduction: Decimal
    exempt_65: Decimal
    deductions: Decimal

    def as_dict(self):
        return {"base": str(self.base), "imposto": str(self.tax), "aliquota": str(self.rate), "metodo": self.method,
                "reducao_lei_15270": str(self.reduction), "parcela_isenta_65": str(self.exempt_65),
                "deducoes": str(self.deductions)}


def compute_ir(table: IrTable, *, taxable: Decimal, pension_income: Decimal, contribution: Decimal,
               dependents: int, alimony: Decimal, over_65: bool, molestia: bool, decimo: bool = False) -> IrResult:
    """pension_income = parte de 'taxable' que é provento de aposentadoria/pensão (base da parcela isenta 65+)."""
    if molestia:
        return IrResult(ZERO, ZERO, ZERO, "ISENTO_MOLESTIA", ZERO, ZERO, ZERO)
    exempt = min(pension_income, table.exempt_65) if over_65 else ZERO
    gross = max(ZERO, taxable - exempt)
    legal_ded = contribution + table.dependent * dependents + alimony
    base_legal = max(ZERO, gross - legal_ded)
    base_simpl = max(ZERO, gross - table.simplified)
    tax_legal, rate_legal = table.tax(base_legal)
    tax_simpl, rate_simpl = table.tax(base_simpl)
    # O desconto simplificado mensal não se aplica ao 13º (tributação exclusiva)
    if not decimo and tax_simpl < tax_legal:
        base, tax, rate, method, ded = base_simpl, tax_simpl, rate_simpl, "SIMPLIFICADO", table.simplified
    else:
        base, tax, rate, method, ded = base_legal, tax_legal, rate_legal, "LEGAL", legal_ded
    red = table.reduce(tax, gross, decimo)
    tax = tax - red
    if base <= 0:
        method = "ISENTO"
    return IrResult(base, tax, rate, method, red, exempt, ded)


def contribution(base: Decimal, ceiling: Decimal, rate: Decimal) -> Decimal:
    """Contribuição de aposentado/pensionista: alíquota sobre o que excede o teto do RGPS."""
    return q(max(ZERO, base - ceiling) * rate)


def rate_on(institution, on: date) -> Decimal:
    from apps.institutions.services import get_parameter

    v = get_parameter(institution, RATE_PARAM, on)
    if v in (None, ""):
        raise BusinessRuleError(
            f"Alíquota de contribuição dos segurados vigente em {on:%m/%Y} não cadastrada (parâmetro '{RATE_PARAM}').")
    return D(v)


def margin_on(institution, on: date) -> Decimal:
    from apps.institutions.services import get_parameter

    return D(get_parameter(institution, MARGIN_PARAM, on, default="0.35"))
