"""Carga inicial da folha: rubricas padrão e parâmetros (IRRF, alíquota, margem consignável)."""
from datetime import date

from django.db import transaction

from apps.institutions.models import Parameter
from apps.institutions.services import set_parameter

from .models import Rubric
from .tax import IR_PARAM, MARGIN_PARAM, RATE_PARAM

# código, descrição, tipo, cálculo, IR, RPPS, 13º, margem, dedutível do IR
DEFAULT_RUBRICS = [
    ("0001", "Proventos de aposentadoria", "PROVENTO", "APOSENTADORIA", True, True, True, True, False),
    ("0002", "Pensão por morte", "PROVENTO", "PENSAO", True, True, True, True, False),
    ("0005", "Retroativo de benefício", "PROVENTO", "RETROATIVO", True, True, False, False, False),
    ("0010", "Gratificação natalina (13º)", "PROVENTO", "DECIMO", True, True, False, False, False),
    ("0050", "Diferença de proventos", "PROVENTO", "MANUAL", True, True, False, False, False),
    ("0051", "Diferença não tributável (indenizatória)", "PROVENTO", "MANUAL", False, False, False, False, False),
    ("0101", "Contribuição previdenciária (RPPS)", "DESCONTO", "CONTRIB_RPPS", False, False, False, False, True),
    ("0102", "Contribuição previdenciária s/ 13º", "DESCONTO", "CONTRIB_13", False, False, False, False, True),
    ("0111", "IRRF", "DESCONTO", "IRRF", False, False, False, False, False),
    ("0112", "IRRF s/ 13º", "DESCONTO", "IRRF_13", False, False, False, False, False),
    ("0113", "IRRF s/ rendimentos acumulados (RRA)", "DESCONTO", "IRRF_RRA", False, False, False, False, False),
    ("0201", "Pensão alimentícia", "DESCONTO", "PENSAO_ALIMENTICIA", False, False, False, False, True),
    ("0202", "Pensão alimentícia s/ 13º", "DESCONTO", "PENSAO_ALIMENTICIA_13", False, False, False, False, True),
    ("0301", "Empréstimo consignado", "DESCONTO", "CONSIGNACAO", False, False, False, False, False),
    ("0302", "Mensalidade sindical / associativa", "DESCONTO", "CONSIGNACAO", False, False, False, False, False),
    ("0303", "Cartão de crédito consignado", "DESCONTO", "CONSIGNACAO", False, False, False, False, False),
    ("0401", "Reposição ao erário", "DESCONTO", "MANUAL", False, False, False, False, False),
    ("0402", "Desconto por decisão judicial", "DESCONTO", "MANUAL", False, False, False, False, False),
]

_FAIXAS_2025 = [["2428.80", "0", "0"], ["2826.65", "0.075", "182.16"], ["3751.05", "0.15", "394.16"],
                ["4664.68", "0.225", "675.49"], [None, "0.275", "908.73"]]
IR_TABLES = [
    (date(2024, 2, 1), {
        "faixas": [["2259.20", "0", "0"], ["2826.65", "0.075", "169.44"], ["3751.05", "0.15", "381.44"],
                   ["4664.68", "0.225", "662.77"], [None, "0.275", "896.00"]],
        "deducao_dependente": "189.59", "desconto_simplificado": "564.80", "parcela_isenta_65": "1903.98",
        "reducao": None, "fonte": "Lei 14.848/2024"}),
    (date(2025, 5, 1), {
        "faixas": _FAIXAS_2025, "deducao_dependente": "189.59", "desconto_simplificado": "607.20",
        "parcela_isenta_65": "1903.98", "reducao": None, "fonte": "MP 1.294/2025 (Lei 15.191/2025)"}),
    (date(2026, 1, 1), {
        "faixas": _FAIXAS_2025, "deducao_dependente": "189.59", "desconto_simplificado": "607.20",
        "parcela_isenta_65": "1903.98",
        "reducao": {"limite_isencao": "5000.00", "reducao_maxima": "312.89", "limite_reducao": "7350.00",
                    "constante": "978.62", "fator": "0.133145", "aplica_13": True},
        "fonte": "Lei 15.270/2025 — CONFERIR valores antes do uso"}),
]


@transaction.atomic
def seed_payroll(institution) -> dict:
    created = {"rubricas": 0, "parametros": []}
    for code, name, kind, calc, ir, rpps, d13, margem, ded in DEFAULT_RUBRICS:
        _, new = Rubric.objects.get_or_create(
            institution=institution, code=code, version=1,
            defaults={"name": name, "kind": kind, "calc": calc, "inc_ir": ir, "inc_rpps": rpps, "inc_13": d13,
                      "inc_margem": margem, "ir_deduction": ded, "valid_from": date(2020, 1, 1)})
        created["rubricas"] += int(new)
    if not Parameter.objects.filter(institution=institution, key=IR_PARAM).exists():
        for i, (start, table) in enumerate(IR_TABLES):
            set_parameter(institution, IR_PARAM, table, start, description="Tabela progressiva mensal do IRRF",
                          change_reason="" if i == 0 else f"Nova tabela — {table['fonte']}")
        created["parametros"].append(IR_PARAM)
    if not Parameter.objects.filter(institution=institution, key=RATE_PARAM).exists():
        set_parameter(institution, RATE_PARAM, "0.14", date(2025, 9, 1),
                      description="Alíquota de contribuição de servidores, aposentados e pensionistas "
                                  "(sugestão: 14% — confira a lei do ente em Arrecadação › Alíquotas)")
        created["parametros"].append(RATE_PARAM)
    if not Parameter.objects.filter(institution=institution, key=MARGIN_PARAM).exists():
        set_parameter(institution, MARGIN_PARAM, "0.35", date(2020, 1, 1),
                      description="Margem consignável (fração da base). Ajustar conforme a lei municipal.")
        created["parametros"].append(MARGIN_PARAM)
    return created
