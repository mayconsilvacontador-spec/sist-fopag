"""Parâmetros da arrecadação (alíquota patronal e dia de vencimento)."""
from datetime import date

from apps.institutions.models import Parameter
from apps.institutions.services import set_parameter

PARAMS = [
    ("arrecadacao.aliquota_patronal", "0.24", date(2025, 9, 1),
     "Alíquota patronal (Emenda à LOM 28/2025 — 24% a partir de 01/09/2025)"),
    ("arrecadacao.vencimento_dia", 20, date(2020, 1, 1),
     "Dia do mês seguinte à competência para vencimento das contribuições (conferir a lei municipal)"),
]


def seed_financeiro(institution) -> list[str]:
    created = []
    for key, value, start, desc in PARAMS:
        if not Parameter.objects.filter(institution=institution, key=key).exists():
            set_parameter(institution, key, value, start, description=desc)
            created.append(key)
    return created
