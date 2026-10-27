"""
Carga inicial do eSocial: parâmetros e SUGESTÕES de incidências das rubricas (S-1010).

As incidências abaixo são sugestões a CONFERIR com o leiaute S-1.3 vigente (Tabela 03 e códigos codIncIRRF /
codIncCPRP). Só preenchem campos vazios — nunca sobrescrevem o que já foi cadastrado. A natureza da rubrica
(natRubr, Tabela 03) não é sugerida: fica como pendência até ser informada em Folha › Rubricas.
"""
from datetime import date

from django.db import transaction

from apps.institutions.models import Parameter
from apps.institutions.services import set_parameter

# forma de cálculo -> (codIncIRRF, codIncCPRP)
SUGGESTED = {
    "APOSENTADORIA": ("11", "11"), "PENSAO": ("11", "11"), "RETROATIVO": ("11", "11"), "DECIMO": ("12", "12"),
    "CONTRIB_RPPS": ("41", "31"), "CONTRIB_13": ("42", "32"), "IRRF": ("31", "00"), "IRRF_13": ("32", "00"),
    "PENSAO_ALIMENTICIA": ("51", "00"), "PENSAO_ALIMENTICIA_13": ("52", "00"), "CONSIGNACAO": ("00", "00"),
}

PARAMS = [
    ("esocial.versao", "S_01_03_00", "Versão do leiaute do eSocial usada nos XMLs"),
    ("esocial.ambiente", 2, "Ambiente do eSocial: 1 = produção, 2 = produção restrita (testes)"),
]


@transaction.atomic
def seed_esocial(institution) -> dict:
    from apps.folha.models import Rubric

    updated = 0
    for r in Rubric.objects.filter(institution=institution):
        irrf, cprp = SUGGESTED.get(r.calc, (None, None))
        if r.calc == "MANUAL":
            if r.kind == "PROVENTO":
                irrf, cprp = ("11" if r.inc_ir else "00"), ("11" if r.inc_rpps else "00")
            else:
                irrf, cprp = "00", "00"
        changed = False
        if irrf and not r.esocial_inc_irrf:
            r.esocial_inc_irrf, changed = irrf, True
        if cprp and not r.esocial_inc_cprp:
            r.esocial_inc_cprp, changed = cprp, True
        if changed:
            Rubric.objects.filter(pk=r.pk).update(esocial_inc_irrf=r.esocial_inc_irrf, esocial_inc_cprp=r.esocial_inc_cprp)
            updated += 1
    created = []
    for key, value, desc in PARAMS:
        if not Parameter.objects.filter(institution=institution, key=key).exists():
            set_parameter(institution, key, value, date(2020, 1, 1), description=desc)
            created.append(key)
    return {"rubricas_atualizadas": updated, "parametros": created}
