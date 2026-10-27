"""Prova de Vida: campanha por ato do órgão, prazo por aniversário, suspensão após tolerância e restabelecimento."""
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.concessao.models import Benefit, BenefitEvent
from apps.institutions.models import PayrollGroup
from apps.institutions.services import ensure_payroll_groups
from apps.people.models import Person
from apps.provadevida.models import LifeProof
from tests.conftest import PASSWORD


def _benefit(inst, cpf, name, birth, kind="APOSENTADORIA"):
    p = Person.objects.create(institution=inst, cpf=cpf, name=name, birth_date=birth, sex=1)
    inst_or = None
    if kind == "PENSAO":
        inst_or = Person.objects.create(institution=inst, cpf="39053344705", name="Instituidor", birth_date=date(1940, 1, 1),
                                        sex=2, death_date=date(2019, 12, 1))
    return Benefit.objects.create(institution=inst, kind=kind, beneficiary=p, instituidor=inst_or, start_date=date(2020, 1, 1),
                                  amount=Decimal("3000.00"),
                                  payroll_group=PayrollGroup.objects.get(institution=inst, segment="FINANCEIRO"))


def test_campanha_completa(institution, master, client_for):
    ensure_payroll_groups(institution)
    today = timezone.localdate()
    ana = _benefit(institution, "52998224725", "Ana", date(1950, today.month, 10))
    bia = _benefit(institution, "11144477735", "Bia", date(1955, 1, 5), kind="PENSAO")
    c = client_for(master)
    body = {"name": "Prova de vida extraordinária", "kind": "EXTRAORDINARIA", "legal_act": "Decreto nº 10/2026",
            "start_date": (today - timedelta(days=120)).isoformat(), "end_date": (today - timedelta(days=40)).isoformat(),
            "grace_days": 10, "audience": "TODOS", "deadline_rule": "FIM_CAMPANHA",
            "instructions": "Compareça à sede com documento com foto."}
    assert c.post("/api/v1/provadevida/campanhas/", {**body, "legal_act": ""}, format="json").status_code in (400, 409)
    cid = c.post("/api/v1/provadevida/campanhas/", body, format="json").json()["id"]
    r = c.post(f"/api/v1/provadevida/campanhas/{cid}/open/").json()
    assert r["incluidos"] == 2 and r["status"] == "ABERTA"

    # Ana faz a prova; Bia não
    pa = LifeProof.objects.get(campaign_id=cid, person=ana.beneficiary)
    r = c.post(f"/api/v1/provadevida/provas/{pa.pk}/register/", {"done_date": (today - timedelta(days=60)).isoformat(),
               "channel": "PRESENCIAL"}, format="multipart")
    assert r.status_code == 200 and r.json()["status"] == "REALIZADA"

    # Suspensão dos atrasados exige senha; só a Bia é suspensa
    assert c.post(f"/api/v1/provadevida/campanhas/{cid}/suspend/", {}, format="json").status_code == 409
    r = c.post(f"/api/v1/provadevida/campanhas/{cid}/suspend/", {"password": PASSWORD}, format="json").json()
    assert r["pessoas"] == 1 and r["beneficios"] == 1
    bia.refresh_from_db()
    assert bia.status == "SUSPENSO" and BenefitEvent.objects.filter(benefit=bia, kind="SUSPENSAO").exists()

    # Portal: aviso de suspensão
    from apps.provadevida.services import portal_pending

    assert portal_pending(bia.beneficiary).first().status == "BLOQUEADO"

    # Prova tardia da Bia restabelece o benefício (com senha)
    pb = LifeProof.objects.get(campaign_id=cid, person=bia.beneficiary)
    assert c.post(f"/api/v1/provadevida/provas/{pb.pk}/register/", {"done_date": today.isoformat(), "channel": "VISITA"},
                  format="multipart").status_code == 409
    r = c.post(f"/api/v1/provadevida/provas/{pb.pk}/register/", {"done_date": today.isoformat(), "channel": "VISITA",
               "password": PASSWORD}, format="multipart")
    assert r.status_code == 200 and r.json()["restabelecidos"] == 1
    bia.refresh_from_db()
    assert bia.status == "ATIVO" and BenefitEvent.objects.filter(benefit=bia, kind="RESTABELECIMENTO").exists()

    # Listas por situação e relatório
    assert len(c.get(f"/api/v1/provadevida/provas/?campanha={cid}&situacao=REALIZADA").json()["results"]) == 2
    rep = c.get(f"/api/v1/reports/prova-vida-resumo/").json()
    assert rep["linhas"][0]["realizadas"] == 2 and rep["linhas"][0]["percentual"] == 100.0


def test_prazo_no_mes_de_aniversario(institution):
    from apps.provadevida.models import LifeProofCampaign
    from apps.provadevida.services import due_date_for

    camp = LifeProofCampaign(institution=institution, name="Anual", kind="ANUAL", legal_act="Decreto 1/2026",
                             start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), deadline_rule="MES_ANIVERSARIO")
    assert due_date_for(camp, Person(birth_date=date(1950, 2, 14))) == date(2026, 2, 28)
    semestral = LifeProofCampaign(institution=institution, name="1º semestre", kind="SEMESTRAL", legal_act="Decreto 2/2026",
                                  start_date=date(2026, 1, 1), end_date=date(2026, 6, 30), deadline_rule="MES_ANIVERSARIO")
    # Aniversário fora do período: prazo é o fim da campanha
    assert due_date_for(semestral, Person(birth_date=date(1950, 9, 3))) == date(2026, 6, 30)
