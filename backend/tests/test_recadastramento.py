"""Recadastramento: campanha, envio pelo Portal, conferência (antes/depois), devolução, aprovação e presencial."""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.cadastros.models import Ente, Organ, Position
from apps.concessao.models import Benefit
from apps.employment.models import EmploymentLink
from apps.institutions.models import PayrollGroup
from apps.institutions.services import ensure_payroll_groups
from apps.people.models import Address, Document, Person
from apps.portal.models import PortalNotification
from apps.recadastramento import services as rc
from apps.recadastramento.models import Reregistration
from tests.test_portal_prova_vida import _portal_client

DADOS = {"pessoa": {"mobile": "(24) 99999-1234", "email": "ana@exemplo.com", "marital_status": 3, "race": 3,
                    "phone": "", "social_name": "", "education": "Superior"},
         "endereco": {"cep": "27310-400", "street": "Rua Luiz Ponce", "number": "263", "district": "Centro",
                      "city": "Barra Mansa", "uf": "rj", "complement": ""}}
DECL = {"veracidade": True, "dependentes_alteracoes": "Incluir neta sob guarda judicial", "acumula_cargo": False}


def _pdf(x=b"conta"):
    return SimpleUploadedFile("comp.pdf", b"%PDF-1.4 " + x, content_type="application/pdf")


def test_recadastramento_completo(institution, master, client_for):
    ensure_payroll_groups(institution)
    staff = client_for(master)
    today = timezone.localdate()
    ana = Person.objects.create(institution=institution, cpf="52998224725", name="Ana", birth_date=date(1950, 3, 3), sex=1,
                                mobile="(24) 98888-0000")
    Benefit.objects.create(institution=institution, kind="APOSENTADORIA", beneficiary=ana, start_date=date(2020, 1, 1),
                           amount=Decimal("3000"), payroll_group=PayrollGroup.objects.get(institution=institution, segment="FINANCEIRO"))
    org = Organ.objects.create(institution=institution, ente=Ente.objects.create(institution=institution, name="M"), name="Prefeitura")
    bob = Person.objects.create(institution=institution, cpf="11144477735", name="Bob", birth_date=date(1980, 1, 1), sex=2)
    EmploymentLink.objects.create(institution=institution, person=bob, organ=org, registration="1",
                                  position=Position.objects.create(institution=institution, name="Agente", cargo_type=7),
                                  public_service_start=date(2010, 1, 1), ente_start=date(2010, 1, 1), position_start=date(2010, 1, 1))

    cid = staff.post("/api/v1/recadastramento/campanhas/", {
        "name": "Recadastramento 2026", "legal_act": "Decreto nº 9/2026", "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=10)).isoformat(), "audience": "TODOS", "portal_enabled": True,
        "require_residence_proof": True}, format="json").json()["id"]
    assert staff.post(f"/api/v1/recadastramento/campanhas/{cid}/open/").json()["incluidos"] == 2
    item = Reregistration.objects.get(campaign_id=cid, person=ana)
    assert item.group == "BENEFICIARIO" and Reregistration.objects.get(campaign_id=cid, person=bob).group == "SERVIDOR"
    assert PortalNotification.objects.filter(person=ana, key__endswith=":aberta").exists()
    assert rc.reminders(institution) >= 1  # faltam 10 dias -> faixa de 15

    portal = _portal_client(staff, ana)
    data = portal.get("/api/v1/portal/recadastramento/").json()
    assert data["itens"][0]["aceita_portal"] and data["cadastro"]["pessoa"]["mobile"] == "(24) 98888-0000"
    url = f"/api/v1/portal/recadastramento/{item.pk}/enviar/"
    # Sem comprovante (exigido pela campanha) e sem declaração: recusa
    assert portal.post(url, {"dados": json.dumps(DADOS), "declaracoes": json.dumps(DECL)}, format="multipart").status_code == 409
    assert portal.post(url, {"dados": json.dumps(DADOS), "declaracoes": "{}", "comprovante": _pdf()}, format="multipart").status_code == 409
    r = portal.post(url, {"dados": json.dumps(DADOS), "declaracoes": json.dumps(DECL), "comprovante": _pdf()}, format="multipart")
    assert r.status_code == 200 and r.json()["situacao"] == "ENVIADO"
    # Nada muda no cadastro antes da conferência
    ana.refresh_from_db()
    assert ana.mobile == "(24) 98888-0000" and not Address.objects.filter(person=ana).exists()

    # Equipe vê o antes/depois e devolve
    row = staff.get(f"/api/v1/recadastramento/itens/{item.pk}/?grupo=BENEFICIARIO").json()
    assert {m["campo"] for m in row["mudancas"]} >= {"mobile", "email", "street", "city"}
    assert staff.post(f"/api/v1/recadastramento/itens/{item.pk}/give-back/?grupo=BENEFICIARIO",
                      {"reason": "Comprovante ilegível, envie outro."}, format="json").json()["status"] == "DEVOLVIDO"
    assert PortalNotification.objects.filter(person=ana, key__contains=":devolvido").exists()
    portal.post(url, {"dados": json.dumps(DADOS), "declaracoes": json.dumps(DECL), "comprovante": _pdf(b"novo")}, format="multipart")

    r = staff.post(f"/api/v1/recadastramento/itens/{item.pk}/approve/?grupo=BENEFICIARIO", {}, format="json").json()
    assert r["status"] == "APROVADO" and "neta" in r["staff_followup"]
    ana.refresh_from_db()
    assert ana.mobile == "(24) 99999-1234" and ana.email == "ana@exemplo.com" and ana.marital_status == 3
    addr = Address.objects.get(person=ana, valid_to__isnull=True)
    assert addr.street == "Rua Luiz Ponce" and addr.uf == "RJ" and addr.cep == "27310400"
    assert Document.objects.filter(person=ana, doc_type="RESIDENCIA").exists()

    # Presencial (servidor): a equipe preenche e já aprova
    it2 = Reregistration.objects.get(campaign_id=cid, person=bob)
    r = staff.post(f"/api/v1/recadastramento/itens/{it2.pk}/presential/?grupo=SERVIDOR",
                   {"dados": json.dumps({**DADOS, "pessoa": {**DADOS["pessoa"], "mobile": "(24) 97777-0000"}}),
                    "declaracoes": json.dumps({"veracidade": True}), "comprovante": _pdf(b"bob")}, format="multipart")
    assert r.status_code == 200 and r.json()["status"] == "APROVADO" and r.json()["channel"] == "PRESENCIAL"
    bob.refresh_from_db()
    assert bob.mobile == "(24) 97777-0000"

    rep = staff.get("/api/v1/reports/recadastramento-resumo/").json()
    assert rep["linhas"][0]["aprovados"] == 2
