"""Folha de Ativos: vencimento pela tabela (com vigência), adicional por tempo, lançamentos, faltas, RPPS, IRRF e ciclo."""
from datetime import date
from decimal import Decimal

from apps.cadastros.models import Ente, Organ, Position
from apps.employment.models import EmploymentLink, FunctionalEvent
from apps.folha.tax import IrTable, compute_ir
from apps.institutions.services import set_parameter
from apps.pessoal.models import ActiveRubric, SalaryScale

from .test_fase5 import folha, person  # noqa: F401 (fixture com IR, teto e alíquota)

URL = "/api/v1/ativos"


def _cenario(inst):
    set_parameter(inst, "arrecadacao.aliquota_patronal", "0.24", date(2025, 9, 1))
    organ = Organ.objects.create(institution=inst, ente=Ente.objects.create(institution=inst, name="Município"),
                                 name="Prefeitura (fictícia)")
    pos = Position.objects.create(institution=inst, name="AGENTE ADMINISTRATIVO")
    p = person(inst, 400000001, "Servidora Ativa", date(1980, 5, 5))
    link = EmploymentLink.objects.create(institution=inst, person=p, organ=organ, position=pos, registration="5001",
                                         public_service_start=date(2016, 1, 1), ente_start=date(2016, 1, 1),
                                         position_start=date(2016, 1, 1), class_level="B", segment="PREVIDENCIARIO")
    FunctionalEvent.objects.create(institution=inst, link=link, event_type="FALTAS", start_date=date(2025, 10, 6),
                                   end_date=date(2025, 10, 7), days=2, with_pay=False, contributed=False,
                                   counts_as_service=False, description="2 faltas")
    return organ, pos, link


def test_folha_de_ativos_calculo_e_ciclo(institution, master, consulta, client_for, folha):  # noqa: F811
    c = client_for(master)
    organ, pos, link = _cenario(institution)
    # tabela de vencimentos com reajuste: o valor antigo é encerrado, não apagado
    assert c.post(f"{URL}/vencimentos/", {"position": str(pos.pk), "level": "B", "amount": "4500.00",
                                          "valid_from": "2025-01-01"}, format="json").status_code == 201
    r = c.post(f"{URL}/vencimentos/", {"position": str(pos.pk), "level": "B", "amount": "5000.00",
                                       "valid_from": "2025-09-01", "legal_basis": "Lei fictícia 1/2025"}, format="json")
    assert r.status_code == 201, r.json()
    assert SalaryScale.objects.get(amount=Decimal("4500.00")).valid_to == date(2025, 8, 31)

    rubs = {x["code"]: x for x in c.get(f"{URL}/rubricas/").json()}  # sugestão criada no 1º acesso
    assert rubs["1002"]["calc"] == "ADICIONAL_TEMPO"
    r = c.post(f"{URL}/lancamentos/", {"link": str(link.pk), "rubric": rubs["1010"]["id"], "amount": "500.00",
                                       "start": "2025-10-01", "installments": 2}, format="json")
    assert r.status_code == 201, r.json()
    assert c.post(f"{URL}/lancamentos/", {"link": str(link.pk), "rubric": rubs["2001"]["id"], "amount": "10",
                                          "start": "2025-10-01"}, format="json").status_code == 409  # automática

    assert client_for(consulta).post(f"{URL}/folhas/", {"orgao": str(organ.pk), "ano": 2025, "mes": 10},
                                     format="json").status_code == 403
    run = c.post(f"{URL}/folhas/", {"orgao": str(organ.pk), "ano": 2025, "mes": 10}, format="json").json()
    calc = c.post(f"{URL}/folhas/{run['id']}/calcular/").json()
    assert calc["status"] == "CALCULADA" and calc["totals"]["servidores"] == 1
    slips = c.get(f"{URL}/folhas/{run['id']}/contracheques/").json()["results"]
    slip = c.get(f"{URL}/folhas/{run['id']}/contracheques/{slips[0]['id']}/").json()
    items = {i["code"]: Decimal(i["amount"]) for i in slip["items"]}
    # 5.000 (tabela vigente) + 15% (3 triênios em 9 anos) + 500 gratificação − 2 faltas (5.000/30×2)
    assert items["1001"] == Decimal("5000.00") and items["1002"] == Decimal("750.00")
    assert items["1010"] == Decimal("500.00") and items["2003"] == Decimal("333.33")
    base = Decimal("5916.67")
    assert Decimal(slip["rpps_base"]) == base and items["2001"] == Decimal("828.33")  # 14%
    assert Decimal(slip["employer_contribution"]) == Decimal("1420.00")  # 24% patronal (informativo)
    ir = compute_ir(IrTable.load(institution, date(2025, 10, 1)), taxable=base, pension_income=Decimal(0),
                    contribution=Decimal("828.33"), dependents=0, alimony=Decimal(0), over_65=False, molestia=False)
    assert items.get("2002", Decimal(0)) == ir.tax
    assert Decimal(slip["net"]) == Decimal("6250.00") - Decimal("333.33") - Decimal("828.33") - ir.tax

    # ciclo: conferir, fechar (parcela baixa), não recalcula, reabre com justificativa
    assert c.post(f"{URL}/folhas/{run['id']}/conferir/").json()["status"] == "CONFERIDA"
    assert c.post(f"{URL}/folhas/{run['id']}/fechar/").json()["status"] == "FECHADA"
    assert link.active_entries.get().paid_installments == 1
    assert c.post(f"{URL}/folhas/{run['id']}/calcular/").status_code == 409
    assert c.post(f"{URL}/folhas/{run['id']}/excluir/", {"justification": "Aberta por engano no teste"},
                  format="json").status_code == 409
    assert c.post(f"{URL}/folhas/{run['id']}/reabrir/", {"justification": "curta"}, format="json").status_code == 409
    r = c.post(f"{URL}/folhas/{run['id']}/reabrir/", {"justification": "Correção de lançamento do mês"}, format="json")
    assert r.json()["status"] == "CONFERIDA" and link.active_entries.get().paid_installments == 0
    # previdência complementar: base limitada ao teto do RGPS
    link.complementary_pension = True
    link.save()
    ActiveRubric.objects.filter(code="1010").update(inc_rpps=False)
    calc = c.post(f"{URL}/folhas/{run['id']}/calcular/").json()
    assert Decimal(calc["totals"]["base_rpps"]) == Decimal("5416.67")  # abaixo do teto 2025 (8.157,41)
