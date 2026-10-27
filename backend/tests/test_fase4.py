from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.cadastros.models import Ente, Organ, Position
from apps.concessao.models import Benefit, BenefitEvent
from apps.employment.models import EmploymentLink, FunctionalEvent
from apps.institutions.models import Parameter
from apps.institutions.services import ensure_payroll_groups, set_parameter
from apps.people.models import Dependency, Person
from apps.previdencia.rules import seed_rules
from apps.protocolo.models import ProcessType, Sector
from tests.conftest import concluir, historico

REFORM = date(2025, 6, 15)


@pytest.fixture
def base(institution, master):
    seed_rules(institution, REFORM)
    set_parameter(institution, "previdencia.vigencia_reforma_local", REFORM.isoformat(), REFORM)
    set_parameter(institution, "rgps.teto", "8157.41", date(2025, 1, 1))
    set_parameter(institution, "rgps.teto", "8400.00", date(2026, 1, 1), change_reason="Reajuste anual")
    ensure_payroll_groups(institution)
    ente = Ente.objects.create(institution=institution, name="Município")
    organ = Organ.objects.create(institution=institution, ente=ente, name="Prefeitura")
    pos = Position.objects.create(institution=institution, name="Agente", cargo_type=7)
    sector = Sector.objects.create(institution=institution, name="Benefícios", code="BEN")
    sector.members.add(master)
    ptype = ProcessType.objects.create(institution=institution, name="Aposentadoria", deadline_days=60)
    return {"organ": organ, "pos": pos, "sector": sector, "ptype": ptype}


def open_process(c, base, person_id, subject):
    r = c.post("/api/v1/protocol/processes/", {"process_type": str(base["ptype"].pk), "sector": str(base["sector"].pk),
                                               "subject": subject, "interested": person_id, "interested_name": "x"},
               format="json")
    assert r.status_code == 201, r.json()
    return r.json()["id"]


def test_aposentadoria_fluxo_completo_e_pensao(institution, master, client_for, base, setores):
    c = client_for(master)
    p = Person.objects.create(institution=institution, cpf="52998224725", name="José", birth_date=date(1958, 3, 10), sex=2)
    link = EmploymentLink.objects.create(
        institution=institution, person=p, organ=base["organ"], position=base["pos"], registration="10",
        public_service_start=date(1988, 1, 4), ente_start=date(1988, 1, 4), position_start=date(1988, 1, 4),
        career_start=date(1988, 1, 4), segment="FINANCEIRO", base_salary=Decimal("5000.00"))
    historico(institution, p, date(1994, 7, 1), date(2026, 8, 1), "5200.00")

    pid = open_process(c, base, str(p.pk), "Aposentadoria voluntária")
    r = c.post("/api/v1/concessoes/", {"kind": "APOSENTADORIA", "person": str(p.pk), "process": pid}, format="json")
    assert r.status_code == 201, r.json()
    cid = r.json()["id"]

    # Regra não cumprida na data (compulsória só aos 75 anos, em 2033) -> recusa
    bad = c.post(f"/api/v1/concessoes/{cid}/frame/", {"rule": "COMPULSORIA", "validity_date": "2026-09-01",
                                                      "validity_class": 3}, format="json")
    assert bad.status_code == 409
    # EC 41 art. 6º (ingresso até 2003; 60 anos e 35 de contribuição antes de 15/06/2025) -> integralidade
    ok = c.post(f"/api/v1/concessoes/{cid}/frame/", {"rule": "EC41_ART6", "validity_date": "2026-09-01",
                                                     "validity_class": 3}, format="json")
    assert ok.status_code == 200, ok.json()
    calc = c.post(f"/api/v1/concessoes/{cid}/calculate/").json()
    assert calc["integralidade"] is True and Decimal(calc["total"]) == Decimal("5200.00")
    today = timezone.localdate().isoformat()
    imp = concluir(client_for, setores, cid, "123/2026", today)
    assert imp["stage"] == "IMPLANTADO"
    ben = Benefit.objects.get(beneficiary=p, kind="APOSENTADORIA")
    assert ben.payroll_group.segment == "FINANCEIRO" and ben.amount == Decimal("5200.00") and ben.paridade
    link.refresh_from_db()
    assert link.status == "APOSENTADO" and FunctionalEvent.objects.filter(link=link, event_type="APOSENTADORIA").exists()
    ficha = c.get(f"/api/v1/concessoes/{cid}/ficha/").json()
    assert ficha["passos"]["5_proventos"]["total"] == "5200.00"

    # Revisão do benefício: não é mais direta — exige processo próprio (Jurídico → Presidência → publicação)
    assert c.post(f"/api/v1/beneficios/{ben.pk}/event/", {"kind": "REVISAO", "date": "2026-11-01", "amount": "5300,00",
                                                         "justification": "Revisão por paridade"},
                  format="json").status_code == 409
    pid_rev = open_process(c, base, str(p.pk), "Revisão de aposentadoria")
    cid_rev = c.post("/api/v1/concessoes/", {"kind": "REVISAO", "benefit": str(ben.pk), "process": pid_rev},
                     format="json").json()["id"]
    beneficios = client_for(setores["beneficios"])
    r = beneficios.post(f"/api/v1/concessoes/{cid_rev}/revision/", {"amount": "5.300,00", "validity_date": "2026-11-01",
                        "reason": "Revisão por paridade com o cargo em atividade (reajuste geral)."}, format="json")
    assert r.status_code == 200, r.json()
    concluir(client_for, setores, cid_rev, "200/2026", today, revisao=True)
    ben.refresh_from_db()
    assert ben.amount == Decimal("5300.00")

    # Pensão: óbito do aposentado, viúva de 50 anos e filho de 15 -> cota 70%, cotas iguais
    widow = Person.objects.create(institution=institution, cpf="11144477735", name="Maria", birth_date=date(1976, 1, 1), sex=1)
    son = Person.objects.create(institution=institution, cpf="39053344705", name="João", birth_date=date(2011, 5, 5), sex=2)
    Dependency.objects.create(institution=institution, holder=p, dependent=widow, kind=1, start_date=date(2000, 1, 1))
    Dependency.objects.create(institution=institution, holder=p, dependent=son, kind=3, start_date=date(2011, 5, 5))
    p.death_date = date(2026, 12, 1)
    p.save()
    pid2 = open_process(c, base, str(p.pk), "Pensão por morte")
    cid2 = c.post("/api/v1/concessoes/", {"kind": "PENSAO", "person": str(p.pk), "process": pid2}, format="json").json()["id"]
    pc = c.post(f"/api/v1/concessoes/{cid2}/calculate/").json()
    assert Decimal(pc["total"]) == Decimal("3710.00")  # 5300 × 70%
    quotas = {q["dependent_name"]: q for q in pc["quotas"]}
    assert quotas["Maria"]["duration"] == "VITALICIA" and quotas["João"]["end_date"] == "2032-05-05"
    assert concluir(client_for, setores, cid2, "9/2027", today)["stage"] == "IMPLANTADO"
    assert Benefit.objects.filter(kind="PENSAO", instituidor=p).count() == 2
    ben.refresh_from_db()
    assert ben.status == "CESSADO"  # aposentadoria cessada pelo óbito
    assert BenefitEvent.objects.filter(benefit=ben, kind="CESSACAO").exists()


def test_pensao_regra_antiga_e_permissoes(institution, master, consulta, client_for, base):
    c = client_for(master)
    p = Person.objects.create(institution=institution, cpf="52998224725", name="Ana", birth_date=date(1960, 1, 1), sex=1,
                              death_date=date(2024, 3, 1))
    EmploymentLink.objects.create(
        institution=institution, person=p, organ=base["organ"], position=base["pos"], registration="20",
        public_service_start=date(1990, 1, 1), ente_start=date(1990, 1, 1), position_start=date(1990, 1, 1),
        base_salary=Decimal("10000.00"))
    viuvo = Person.objects.create(institution=institution, cpf="11144477735", name="Carlos", birth_date=date(1958, 1, 1), sex=2)
    Dependency.objects.create(institution=institution, holder=p, dependent=viuvo, kind=1, start_date=date(1985, 1, 1))
    pid = open_process(c, base, str(p.pk), "Pensão")
    assert client_for(consulta).post("/api/v1/concessoes/", {"kind": "PENSAO", "person": str(p.pk), "process": pid},
                                     format="json").status_code == 403
    cid = c.post("/api/v1/concessoes/", {"kind": "PENSAO", "person": str(p.pk), "process": pid}, format="json").json()["id"]
    assert c.post(f"/api/v1/concessoes/{cid}/calculate/").status_code == 409  # sem teto de 2024 cadastrado

    Parameter.objects.create(institution=institution, key="rgps.teto", value="7786.02", version=0,
                             valid_from=date(2024, 1, 1), valid_to=date(2024, 12, 31))
    calc = c.post(f"/api/v1/concessoes/{cid}/calculate/").json()
    # Óbito antes da reforma: até o teto (7.786,02) + 70% do excedente sobre 10.000,00 = 9.335,81
    assert calc["total"] == "9335.81" and calc["calculation"]["cotas_reversiveis"] is True
