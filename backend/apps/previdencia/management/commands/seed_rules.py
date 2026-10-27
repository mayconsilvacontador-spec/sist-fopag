"""
Carrega as regras de aposentadoria (EC 103 + Emenda à Lei Orgânica) para uma instituição.

    python manage.py seed_rules --institution PREVIBAM --reforma 2025-06-15

--reforma = início da vigência local da reforma (Barra Mansa: LC 106/2025, publicada em 15/06/2025,
que dá vigência à Emenda à LOM nº 28/2025). Regras já cadastradas não são alteradas.
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.institutions.models import Institution
from apps.institutions.services import set_parameter
from apps.previdencia.rules import seed_rules


class Command(BaseCommand):
    help = "Carrega as regras de aposentadoria de uma instituição."

    def add_arguments(self, parser):
        parser.add_argument("--institution", required=True)
        parser.add_argument("--reforma", required=True, help="AAAA-MM-DD")

    def handle(self, *args, **opts):
        inst = Institution.objects.filter(short_name__iexact=opts["institution"]).first()
        if inst is None:
            raise CommandError("Instituição não encontrada.")
        reform = date.fromisoformat(opts["reforma"])
        n = seed_rules(inst, reform)
        try:
            set_parameter(inst, "previdencia.vigencia_reforma_local", reform.isoformat(), reform,
                          description="Início da vigência local da reforma da previdência (EC 103)")
        except Exception:
            pass  # já cadastrado
        seed_rgps_ceiling(inst)
        self.stdout.write(self.style.SUCCESS(f"{n} regra(s) incluída(s) para {inst.short_name}."))


# Limite máximo dos benefícios do RGPS (portarias interministeriais anuais). Anos seguintes: cadastrar em Parâmetros.
RGPS_CEILING = [(date(2023, 1, 1), "7507.49"), (date(2024, 1, 1), "7786.02"), (date(2025, 1, 1), "8157.41")]

# Séries históricas usadas nos limites mês a mês da média (Lei 3.965/2011, art. 62, § 6º). Valores nominais das
# normas federais de cada época — CONFERIR com a tabela oficial antes de uso em concessão (editáveis em Parâmetros).
RGPS_CEILING_HISTORY = [
    ("1994-07-01", "582.86"), ("1995-05-01", "832.66"), ("1996-05-01", "957.56"), ("1997-06-01", "1031.87"),
    ("1998-06-01", "1081.50"), ("1998-12-16", "1200.00"), ("1999-06-01", "1255.32"), ("2000-06-01", "1328.25"),
    ("2001-06-01", "1430.00"), ("2002-06-01", "1561.56"), ("2003-06-01", "1869.34"), ("2004-01-01", "2400.00"),
    ("2004-05-01", "2508.72"), ("2005-05-01", "2668.15"), ("2006-04-01", "2801.56"), ("2006-08-01", "2801.82"),
    ("2007-04-01", "2894.28"), ("2008-03-01", "3038.99"), ("2009-02-01", "3218.90"), ("2010-01-01", "3416.54"),
    ("2010-06-16", "3467.40"), ("2011-01-01", "3689.66"), ("2012-01-01", "3916.20"), ("2013-01-01", "4159.00"),
    ("2014-01-01", "4390.24"), ("2015-01-01", "4663.75"), ("2016-01-01", "5189.82"), ("2017-01-01", "5531.31"),
    ("2018-01-01", "5645.80"), ("2019-01-01", "5839.45"), ("2020-01-01", "6101.06"), ("2021-01-01", "6433.57"),
    ("2022-01-01", "7087.22"),
]
MINIMUM_WAGE_HISTORY = [
    ("1994-07-01", "64.79"), ("1994-09-01", "70.00"), ("1995-05-01", "100.00"), ("1996-05-01", "112.00"),
    ("1997-05-01", "120.00"), ("1998-05-01", "130.00"), ("1999-05-01", "136.00"), ("2000-04-01", "151.00"),
    ("2001-04-01", "180.00"), ("2002-04-01", "200.00"), ("2003-04-01", "240.00"), ("2004-05-01", "260.00"),
    ("2005-05-01", "300.00"), ("2006-04-01", "350.00"), ("2007-04-01", "380.00"), ("2008-03-01", "415.00"),
    ("2009-02-01", "465.00"), ("2010-01-01", "510.00"), ("2011-01-01", "540.00"), ("2011-03-01", "545.00"),
    ("2012-01-01", "622.00"), ("2013-01-01", "678.00"), ("2014-01-01", "724.00"), ("2015-01-01", "788.00"),
    ("2016-01-01", "880.00"), ("2017-01-01", "937.00"), ("2018-01-01", "954.00"), ("2019-01-01", "998.00"),
    ("2020-01-01", "1039.00"), ("2020-02-01", "1045.00"), ("2021-01-01", "1100.00"), ("2022-01-01", "1212.00"),
    ("2023-01-01", "1302.00"), ("2023-05-01", "1320.00"), ("2024-01-01", "1412.00"), ("2025-01-01", "1518.00"),
    ("2026-01-01", "1621.00"),
]


def seed_rgps_ceiling(inst):
    from apps.institutions.models import Parameter

    if not Parameter.objects.filter(institution=inst, key="rgps.teto").exists():
        for start, value in RGPS_CEILING:
            set_parameter(inst, "rgps.teto", value, start, description="Teto dos benefícios do RGPS (R$)",
                          change_reason="Reajuste anual do teto do RGPS")
    seed_history(inst, "rgps.teto", RGPS_CEILING_HISTORY, "Teto dos benefícios do RGPS (R$)")
    seed_history(inst, "salario_minimo", MINIMUM_WAGE_HISTORY, "Salário mínimo nacional (R$)")


def seed_history(inst, key: str, table, description: str) -> int:
    """
    Inclui as vigências ANTERIORES à primeira já cadastrada (nunca altera versões existentes). Cada faixa termina
    na véspera da seguinte; a última termina na véspera da primeira versão já existente (ou fica aberta).
    """
    from datetime import timedelta

    from django.db.models import Max, Min

    from apps.institutions.models import Parameter

    qs = Parameter.objects.filter(institution=inst, key=key)
    first = qs.aggregate(m=Min("valid_from"))["m"]
    version = qs.aggregate(m=Max("version"))["m"] or 0
    rows = [(date.fromisoformat(d), v) for d, v in table]
    rows = [r for r in rows if first is None or r[0] < first]
    created = 0
    for i, (start, value) in enumerate(rows):
        nxt = rows[i + 1][0] if i + 1 < len(rows) else first
        version += 1
        Parameter.objects.create(institution=inst, key=key, value=value, valid_from=start,
                                 valid_to=nxt - timedelta(days=1) if nxt else None, version=version,
                                 description=description,
                                 change_reason="Série histórica (carga inicial) — conferir com a norma oficial")
        created += 1
    return created
