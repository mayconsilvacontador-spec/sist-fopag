from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cadastros.models import Ente, Organ, Position
from apps.employment.models import EmploymentLink, FunctionalEvent
from apps.people.models import Person
from apps.previdencia.models import Averbacao, RetirementRule
from apps.previdencia.rules import RuleEvaluator, seed_rules
from apps.previdencia.tempo import PersonTime

REFORM = date(2025, 6, 15)
TODAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def setup(institution):
    seed_rules(institution, REFORM)
    ente = Ente.objects.create(institution=institution, name="Município")
    organ = Organ.objects.create(institution=institution, ente=ente, name="Prefeitura", sigfis_code="12")
    pos = Position.objects.create(institution=institution, name="Agente Administrativo", cargo_type=7)
    person = Person.objects.create(institution=institution, cpf="52998224725", name="José", birth_date=date(1962, 5, 10),
                                   sex=2)
    link = EmploymentLink.objects.create(
        institution=institution, person=person, organ=organ, position=pos, registration="100",
        public_service_start=date(1995, 3, 1), ente_start=date(1995, 3, 1), position_start=date(1995, 3, 1),
        career_start=date(1995, 3, 1), segment="FINANCEIRO")
    # INSS privado 1990-01-01 a 1995-12-31 (sobrepõe 1995-03-01..1995-12-31 ao RPPS)
    Averbacao.objects.create(institution=institution, person=person, nature="01", issuer="Empresa X",
                             start_date=date(1990, 1, 1), end_date=date(1995, 12, 31), certified_days=2191)
    return {"person": person, "link": link, "organ": organ, "pos": pos}


def test_tempo_deducoes_e_concomitancia(setup):
    link = setup["link"]
    FunctionalEvent.objects.create(institution=link.institution, link=link, event_type="LICENCA",
                                   start_date=date(2000, 1, 1), end_date=date(2000, 1, 30), counts_as_service=False,
                                   contributed=False, description="Licença sem vencimentos")
    pt = PersonTime(setup["person"])
    s = pt.summary(date(2025, 6, 14))
    rpps = (date(2025, 6, 14) - date(1995, 3, 1)).days + 1 - 30
    overlap = (date(1995, 12, 31) - date(1995, 3, 1)).days + 1
    assert s.contribuicao == rpps + 2191 - overlap
    assert s.servico_publico == rpps  # INSS privado não é serviço público
    assert any("concomitantes" in w for w in pt.warnings)


def test_regras_direito_adquirido_e_permanente(setup):
    ev = RuleEvaluator(setup["person"], today=TODAY)
    rules = {r.code: r for r in RetirementRule.objects.all()}
    art6 = ev.evaluate(rules["EC41_ART6"])
    assert art6.status == "CUMPRIDA" and art6.eligible_date <= date(2025, 6, 14)
    perm = ev.evaluate(rules["EC103_ART10_I"])
    assert perm.status == "CUMPRIRA" and perm.eligible_date == date(2027, 5, 10)  # 65 anos
    # Ingresso em 1995 (antes de 16/12/1998): EC 47 se aplica; 60 anos em 2022 e 35 de contribuição antes da reforma
    ec47 = ev.evaluate(rules["EC47_ART3"])
    assert ec47.status == "CUMPRIDA" and ec47.eligible_date <= date(2025, 6, 14)


def test_transicao_nao_se_aplica_a_quem_ingressou_apos_reforma(institution, setup):
    p = Person.objects.create(institution=institution, cpf="11144477735", name="Ana", birth_date=date(1990, 1, 1), sex=1)
    EmploymentLink.objects.create(institution=institution, person=p, organ=setup["organ"], position=setup["pos"],
                                  registration="200", public_service_start=date(2025, 8, 1), ente_start=date(2025, 8, 1),
                                  position_start=date(2025, 8, 1))
    ev = RuleEvaluator(p, today=TODAY)
    rules = {r.code: r for r in RetirementRule.objects.all()}
    assert ev.evaluate(rules["EC103_ART4"]).status == "NAO_SE_APLICA"
    perm = ev.evaluate(rules["EC103_ART10_I"])
    assert perm.status == "CUMPRIRA" and perm.eligible_date == date(2052, 1, 1)  # 62 anos


def test_simulacao_salarios_salcontr_e_ctc(institution, master, client_for, setup):
    c = client_for(master)
    pid = str(setup["person"].pk)
    sim = c.get(f"/api/v1/previdencia/simulacao/{pid}/")
    assert sim.status_code == 200, sim.json()
    body = sim.json()
    assert body["abono_permanencia"]["data"] is not None
    assert {r["codigo"] for r in body["regras"]} >= {"EC103_ART10_I", "EC41_ART6"}

    csv_ = SimpleUploadedFile("s.csv", "competencia;valor;regime\n07/1994;1.000,00;RPPS\n08/1994;1500,50;RPPS\n13/1994;1;RPPS\n"
                              .encode(), content_type="text/csv")
    r = c.post("/api/v1/previdencia/salarios/import/", {"person": pid, "file": csv_}, format="multipart").json()
    assert r["incluidos"] == 2 and len(r["erros"]) == 1
    txt = c.get(f"/api/v1/previdencia/salarios/salcontr/?person={pid}&ug=12&orgao=34&matricula=100&processo=2026/1")
    lines = txt.content.decode("latin-1").splitlines()
    assert len(lines) == 2 and all(len(x) == 62 for x in lines)
    assert lines[0][:8] == "  12  34" and lines[0][39:45] == "071994" and lines[0][45] == "1"
    assert lines[0][46:] == "0000000000100000"

    payload = {"person": pid, "destination": "INSS", "period_start": "1995-03-01", "period_end": "2020-12-31"}
    assert c.post("/api/v1/previdencia/ctc/", payload, format="json").status_code == 409  # vínculo ativo
    link = setup["link"]
    link.status, link.end_date, link.end_reason = "EXONERADO", date(2020, 12, 31), "Exoneração a pedido"
    link.save()
    ctc = c.post("/api/v1/previdencia/ctc/", payload, format="json")
    assert ctc.status_code == 201, ctc.json()
    snap = ctc.json()["snapshot"]
    assert snap["totais"]["dias_liquidos"] == (date(2020, 12, 31) - date(1995, 3, 1)).days + 1
    assert snap["remuneracoes"] == []  # salários importados (1994) são anteriores ao período certificado
    assert c.post("/api/v1/previdencia/ctc/", payload, format="json").status_code == 409  # período já certificado
    cid = ctc.json()["id"]
    assert c.post(f"/api/v1/previdencia/ctc/{cid}/cancel/", {"justification": "Emitida com erro de período"},
                  format="json").json()["status"] == "CANCELADA"


def test_importacao_de_salarios_em_lote(institution, master, client_for):
    import io
    from decimal import Decimal

    from apps.people.models import Person
    from apps.previdencia.models import ContributionSalary

    a = Person.objects.create(institution=institution, cpf="52998224725", name="Ana", birth_date=date(1970, 1, 1), sex=1)
    b = Person.objects.create(institution=institution, cpf="11144477735", name="Beto", birth_date=date(1971, 1, 1), sex=2)
    csv = ("cpf;competencia;valor;regime;vinculo\n"
           "529.982.247-25;07/1994;1.234,56;RPPS;Prefeitura\n"
           "529.982.247-25;08/1994;1.300,00;RPPS;Prefeitura\n"
           "111.444.777-35;01/2000;2500,00;RGPS;Empresa\n"
           "390.533.447-05;01/2000;999,00;RPPS;X\n"      # CPF não cadastrado
           "529.982.247-25;06/1994;100,00;RPPS;X\n")     # anterior a 07/1994
    f = io.BytesIO(csv.encode("utf-8-sig"))
    f.name = "lote.csv"
    c = client_for(master)
    r = c.post("/api/v1/previdencia/salarios/import-lote/", {"file": f}, format="multipart").json()
    assert r["segurados"] == 2 and r["incluidos"] == 3 and r["cpfs_nao_cadastrados"] == 1 and len(r["erros"]) == 2
    assert ContributionSalary.objects.get(person=a, competence=date(1994, 7, 1)).amount == Decimal("1234.56")
    assert ContributionSalary.objects.get(person=b).regime == "RGPS"
    # Reimportar com valor novo atualiza (não duplica)
    f2 = io.BytesIO("529.982.247-25;07/1994;1.500,00;RPPS;Prefeitura\n".encode())
    f2.name = "lote2.csv"
    r = c.post("/api/v1/previdencia/salarios/import-lote/", {"file": f2}, format="multipart").json()
    assert r["atualizados"] == 1 and r["incluidos"] == 0
    assert ContributionSalary.objects.filter(person=a).count() == 2
