import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from tests.conftest import PASSWORD

from apps.cadastros.models import Bank
from apps.concessao.models import Benefit
from apps.esocial.defaults import seed_esocial
from apps.esocial.models import EsocialEvent
from apps.folha.defaults import seed_payroll
from apps.institutions.models import PayrollGroup
from apps.institutions.services import ensure_payroll_groups, set_parameter
from apps.people.models import Address, BankAccount, Dependency, Person

NS = "{http://www.esocial.gov.br/schema/evt/%s/v_S_01_03_00}"


@pytest.fixture
def base(institution):
    institution.cnpj = "11222333000181"
    institution.save()
    set_parameter(institution, "rgps.teto", "8157.41", date(2025, 1, 1))
    ensure_payroll_groups(institution)
    seed_payroll(institution)
    seed_esocial(institution)
    return PayrollGroup.objects.get(institution=institution, segment="PREVIDENCIARIO")


def _people(inst):
    p = Person.objects.create(institution=inst, cpf="52998224725", name="Maria Teste", birth_date=date(1950, 5, 1), sex=1)
    Address.objects.create(institution=inst, person=p, street="Rua A", number="10", city="Barra Mansa", city_ibge="3300407",
                           uf="RJ", cep="27330000", valid_from=date(2020, 1, 1))
    bank = Bank.objects.create(institution=inst, code="001", name="Banco do Brasil")
    BankAccount.objects.create(institution=inst, person=p, bank=bank, branch="1", account="2", valid_from=date(2020, 1, 1))
    neto = Person.objects.create(institution=inst, cpf="11144477735", name="Neto", birth_date=date(2015, 1, 1), sex=2)
    Dependency.objects.create(institution=inst, holder=p, dependent=neto, kind=11, start_date=date(2015, 1, 1),
                              tax_dependent=True)
    return p


def _ret(items):
    body = "".join(
        f'<retornoEvento Id="{i}"><eSocial><retornoEvento><processamento><cdResposta>{c}</cdResposta>'
        f"<descResposta>{m}</descResposta>"
        + (f"<ocorrencias><ocorrencia><codigo>{oc}</codigo><descricao>Campo inválido</descricao></ocorrencia></ocorrencias>"
           if oc else "")
        + f"</processamento>{f'<recibo><nrRecibo>{r}</nrRecibo></recibo>' if r else ''}</retornoEvento></eSocial></retornoEvento>"
        for i, c, m, r, oc in items)
    return ('<eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/retornoProcessamento/v1_3_0">'
            f"<retornoProcessamentoLoteEventos><retornoEventos>{body}</retornoEventos></retornoProcessamentoLoteEventos>"
            "</eSocial>").encode()


def test_eventos_cadastrais_exportacao_e_retorno(institution, master, consulta, client_for, base):
    c = client_for(master)
    p = _people(institution)
    b = Benefit.objects.create(institution=institution, kind="APOSENTADORIA", beneficiary=p, payroll_group=base,
                               start_date=date(2024, 3, 1), amount=Decimal("9000.00"), registration="777")

    assert client_for(consulta).post("/api/v1/esocial/eventos/generate-registrations/").status_code == 403
    r = c.post("/api/v1/esocial/eventos/generate-registrations/")
    assert r.json() == {"S-2400": 1, "S-2410": 1, "S-2420": 0}
    assert c.post("/api/v1/esocial/eventos/generate-registrations/").json() == {"S-2400": 0, "S-2410": 0, "S-2420": 0}

    s2400 = EsocialEvent.objects.get(event_type="S-2400")
    assert s2400.status == "VALIDADO", s2400.pendencies
    root = ET.fromstring(s2400.xml)
    evt = root.find(NS % "evtCdBenefIn" + "evtCdBenefIn")
    assert len(evt.get("Id")) == 36 and evt.get("Id").startswith("ID111222333000181")
    ben = evt.find(NS % "evtCdBenefIn" + "beneficiario")
    assert ben.findtext(NS % "evtCdBenefIn" + "sexo") == "F"
    assert ben.find(NS % "evtCdBenefIn" + "dependente").findtext(NS % "evtCdBenefIn" + "tpDep") == "06"

    s2410 = EsocialEvent.objects.get(event_type="S-2410")
    assert s2410.status == "PENDENTE" and any("Tabela 25" in x for x in s2410.pendencies)
    assert "<tpPlanRP>1</tpPlanRP>" in s2410.xml and "<nrBeneficio>777</nrBeneficio>" in s2410.xml
    # Evento com pendência não é exportado
    assert c.post("/api/v1/esocial/eventos/export/", {"ids": [str(s2410.pk)]}, format="json").status_code == 409
    assert c.post(f"/api/v1/beneficios/{b.pk}/esocial/", {"esocial_tp_beneficio": "0101"}, format="json").status_code == 200
    assert c.post(f"/api/v1/esocial/eventos/{s2410.pk}/revalidate/").json()["status"] == "VALIDADO"

    resp = c.post("/api/v1/esocial/eventos/export/", {"ids": [str(s2400.pk), str(s2410.pk)]}, format="json")
    assert resp.status_code == 200 and resp["Content-Type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert f"S-2400/{s2400.event_id}.xml" in names and len(names) == 2
    s2410.refresh_from_db()
    assert s2410.status == "EXPORTADO"

    # Retorno: S-2400 aceito, S-2410 rejeitado
    f = io.BytesIO(_ret([(s2400.event_id, "201", "Sucesso", "1.1.0000000000000000001", ""),
                         (s2410.event_id, "401", "Erro", "", "1234")]))
    f.name = "retorno.xml"
    out = c.post("/api/v1/esocial/eventos/import-return/", {"file": f}, format="multipart").json()
    assert out["registrados"] == 2
    s2400.refresh_from_db()
    s2410.refresh_from_db()
    assert s2400.status == "ACEITO" and s2400.receipt == "1.1.0000000000000000001"
    assert s2410.status == "REJEITADO" and "1234" in s2410.return_message

    # Corrigir o rejeitado gera novo evento; retificar o aceito usa indRetif=2 com o recibo
    new = c.post(f"/api/v1/esocial/eventos/{s2410.pk}/replace/").json()
    s2410.refresh_from_db()
    assert s2410.status == "SUBSTITUIDO" and new["status"] == "VALIDADO" and new["retification"] is False
    ret = c.post(f"/api/v1/esocial/eventos/{s2400.pk}/replace/").json()
    xml = EsocialEvent.objects.get(pk=ret["id"]).xml
    assert ret["retification"] is True and "<indRetif>2</indRetif>" in xml and "<nrRecibo>1.1.0000000000000000001" in xml

    # Retorno manual
    ev = EsocialEvent.objects.get(pk=new["id"])
    c.post("/api/v1/esocial/eventos/export/", {"ids": [str(ev.pk)]}, format="json")
    assert c.post(f"/api/v1/esocial/eventos/{ev.pk}/return/", {"accepted": True}, format="json").status_code == 409
    assert c.post(f"/api/v1/esocial/eventos/{ev.pk}/return/", {"accepted": True, "receipt": "1.2.3"},
                  format="json").json()["status"] == "ACEITO"

    # Término do benefício -> S-2420 (pendente até informar o motivo, Tabela 26)
    c.post(f"/api/v1/beneficios/{b.pk}/event/", {"kind": "CESSACAO", "date": "2026-01-31",
                                                 "justification": "Óbito da beneficiária",
                                                 "password": PASSWORD}, format="json")
    assert c.post("/api/v1/esocial/eventos/generate-registrations/").json()["S-2420"] == 1
    s2420 = EsocialEvent.objects.get(event_type="S-2420")
    assert s2420.status == "PENDENTE" and "<dtTermBeneficio>2026-01-31" in s2420.xml

    hist = c.get("/api/v1/esocial/eventos/history/").json()
    assert hist["count"] >= 8
    summ = c.get("/api/v1/esocial/eventos/summary/").json()
    assert summ["por_evento"]["S-2400"]["ACEITO"] == 1


def test_eventos_periodicos(institution, master, client_for, base):
    c = client_for(master)
    p = _people(institution)
    Benefit.objects.create(institution=institution, kind="APOSENTADORIA", beneficiary=p, payroll_group=base,
                           start_date=date(2024, 3, 1), amount=Decimal("9000.00"), registration="777")
    rid = c.post("/api/v1/folha/folhas/", {"year": 2025, "month": 10, "payroll_group": str(base.pk)},
                 format="json").json()["id"]
    assert c.post("/api/v1/esocial/eventos/generate-payroll/", {"run": rid}, format="json").status_code == 409
    for step in ("calculate", "check", "close"):
        assert c.post(f"/api/v1/folha/folhas/{rid}/{step}/").status_code == 200
    out = c.post("/api/v1/esocial/eventos/generate-payroll/", {"run": rid}, format="json").json()
    assert out == {"S-1207": 1, "S-1210": 0}
    s1207 = EsocialEvent.objects.get(event_type="S-1207")
    assert s1207.status == "VALIDADO", s1207.pendencies
    assert s1207.period == "2025-10" and "<perApur>2025-10</perApur>" in s1207.xml
    assert "<codRubr>0001</codRubr>" in s1207.xml and "<vrRubr>9000.00</vrRubr>" in s1207.xml

    c.post(f"/api/v1/folha/folhas/{rid}/pay/", {"payment_date": "2025-10-30"}, format="json")
    assert c.post("/api/v1/esocial/eventos/generate-payroll/", {"run": rid}, format="json").json() == {"S-1207": 0, "S-1210": 1}
    s1210 = EsocialEvent.objects.get(event_type="S-1210")
    assert "<tpPgto>5</tpPgto>" in s1210.xml and "<dtPgto>2025-10-30</dtPgto>" in s1210.xml

    # Fechamento só depois dos periódicos aceitos
    assert c.post("/api/v1/esocial/eventos/close-period/", {"period": "2025-10"}, format="json").status_code == 409
    for ev in (s1207,):
        c.post("/api/v1/esocial/eventos/export/", {"ids": [str(ev.pk)]}, format="json")
        c.post(f"/api/v1/esocial/eventos/{ev.pk}/return/", {"accepted": True, "receipt": "9.9.9"}, format="json")
    s1210.status, s1210.receipt = "ACEITO", "9.9.8"
    s1210.save()
    fe = c.post("/api/v1/esocial/eventos/close-period/", {"period": "2025-10"}, format="json")
    assert fe.status_code == 201 and fe.json()["event_type"] == "S-1299"
    assert "<evtRemun>S</evtRemun>" in EsocialEvent.objects.get(event_type="S-1299").xml

    # S-1010: rubricas ficam pendentes até informar a natureza (Tabela 03)
    n = c.post("/api/v1/esocial/eventos/generate-rubrics/").json()["S-1010"]
    assert n == 18
    assert EsocialEvent.objects.filter(event_type="S-1010", status="PENDENTE").count() == 18
