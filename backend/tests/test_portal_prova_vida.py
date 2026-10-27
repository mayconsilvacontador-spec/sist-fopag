"""Prova de vida pelo Portal, avisos do segurado, mensagens ao celular e checklist → Cadastro Único."""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.concessao.models import Benefit
from apps.institutions.models import PayrollGroup
from apps.institutions.services import ensure_payroll_groups
from apps.people.models import Address, Document, Person
from apps.portal.models import OutboundMessage, PortalNotification
from apps.provadevida import services as pv
from apps.provadevida.models import LifeProof
from tests.test_concessao_seguranca import caso  # noqa: F401  (fixture: aposentadoria calculada)

NEW = "Nova-Senha-Portal-2026!"


def _png(seed: bytes):
    return SimpleUploadedFile("foto.png", b"\x89PNG\r\n\x1a\n" + seed * 50, content_type="image/png")


def _portal_client(staff, person):
    temp = staff.post("/api/v1/portal-admin/acessos/", {"person": str(person.pk)}, format="json").json()["senha_provisoria"]
    c = APIClient()
    tok = c.post("/api/v1/portal/auth/token/", {"cpf": person.cpf, "password": temp}, format="json").json()["access"]
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
    c.post("/api/v1/auth/change-password/", {"current_password": temp, "new_password": NEW}, format="json")
    tok = c.post("/api/v1/portal/auth/token/", {"cpf": person.cpf, "password": NEW}, format="json").json()["access"]
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
    return c


def test_prova_de_vida_pelo_portal(institution, master, client_for):
    ensure_payroll_groups(institution)
    staff = client_for(master)
    today = timezone.localdate()
    ana = Person.objects.create(institution=institution, cpf="52998224725", name="Ana", birth_date=date(1950, 3, 3),
                                sex=1, mobile="(24) 99876-5432")
    ben = Benefit.objects.create(institution=institution, kind="APOSENTADORIA", beneficiary=ana, start_date=date(2020, 1, 1),
                                 amount=Decimal("3000.00"),
                                 payroll_group=PayrollGroup.objects.get(institution=institution, segment="FINANCEIRO"))
    cid = staff.post("/api/v1/provadevida/campanhas/", {
        "name": "Prova de vida 2026", "kind": "ANUAL", "legal_act": "Decreto nº 5/2026", "start_date": (today - timedelta(days=10)).isoformat(),
        "end_date": (today + timedelta(days=5)).isoformat(), "grace_days": 0, "audience": "TODOS", "deadline_rule": "FIM_CAMPANHA",
        "allow_portal": True, "portal_notice": True}, format="json").json()["id"]
    staff.post(f"/api/v1/provadevida/campanhas/{cid}/open/")

    # Aviso de abertura no sininho + mensagem pronta para o celular (sem provedor: aguardando envio)
    assert PortalNotification.objects.filter(person=ana, key__endswith=":aberta").exists()
    msg = OutboundMessage.objects.get(person=ana)
    assert msg.status == "PENDENTE" and msg.phone == "24998765432"
    row = staff.get("/api/v1/portal-admin/mensagens/?situacao=PENDENTE").json()["results"][0]
    assert row["whatsapp"].startswith("https://wa.me/5524998765432?text=")
    # Lembrete de prazo (faltam 5 dias -> faixa de 7 dias), uma vez só
    assert pv.portal_reminders(institution) == 1
    pv.portal_reminders(institution)
    assert PortalNotification.objects.filter(person=ana, key__contains=":d7").count() == 1

    portal = _portal_client(staff, ana)
    avisos = portal.get("/api/v1/portal/avisos/").json()
    assert avisos["nao_lidos"] >= 2
    proofs = portal.get("/api/v1/portal/prova-de-vida/").json()
    assert proofs[0]["aceita_portal"] is True
    pid = proofs[0]["id"]

    # Envio: exige declaração, duas fotos diferentes e os gestos de vivacidade feitos na câmera ao vivo
    url = f"/api/v1/portal/prova-de-vida/{pid}/enviar/"
    viva = json.dumps({"desafios": ["Olhe de frente", "Vire o rosto para a esquerda"], "movimento": 12.5, "camera": "frontal"})

    def envio(s, d, g=(b"g1", b"g2"), v=viva, decl="true"):
        return {"selfie": _png(s), "documento": _png(d), "gestos": [_png(x) for x in g], "vivacidade": v, "declaracao": decl}

    assert portal.post(url, envio(b"a", b"b", decl="false"), format="multipart").status_code == 409
    assert portal.post(url, envio(b"a", b"a"), format="multipart").status_code == 409
    # Foto da galeria (sem os gestos da câmera) é recusada; movimento insuficiente também
    sem = {"selfie": _png(b"a"), "documento": _png(b"b"), "declaracao": "true"}
    assert "câmera do Portal" in portal.post(url, sem, format="multipart").json()["detail"]
    parada = json.dumps({"desafios": ["Olhe de frente", "Vire à esquerda"], "movimento": 0.5})
    assert portal.post(url, envio(b"a", b"b", v=parada), format="multipart").status_code == 409
    r = portal.post(url, envio(b"a", b"b"), format="multipart")
    assert r.status_code == 200 and r.json()["situacao"] == "EM_ANALISE"

    # Equipe recusa (foto ilegível) -> volta a pendente e o segurado é avisado
    r = staff.post(f"/api/v1/provadevida/provas/{pid}/reject/", {"reason": "Foto do documento ilegível."}, format="json")
    assert r.json()["status"] == "PENDENTE"
    assert PortalNotification.objects.filter(person=ana, key__contains=":recusada").exists()
    assert staff.get(f"/api/v1/provadevida/provas/{pid}/photo/?tipo=documento").status_code == 200

    # Reenvio e aprovação
    portal.post(url, envio(b"c", b"d", g=(b"g3", b"g4")), format="multipart")
    assert staff.get(f"/api/v1/provadevida/provas/{pid}/photo/?tipo=gesto&n=1").status_code == 200
    assert LifeProof.objects.get(pk=pid).portal_liveness["fotos"] == 2
    r = staff.post(f"/api/v1/provadevida/provas/{pid}/register/", {"done_date": today.isoformat(), "channel": "PORTAL"},
                   format="multipart")
    assert r.status_code == 200 and r.json()["status"] == "REALIZADA"
    assert PortalNotification.objects.filter(person=ana, key__endswith=":ok").exists()
    ben.refresh_from_db()
    assert ben.status == "ATIVO"

    # Marcar avisos como lidos
    portal.post("/api/v1/portal/avisos/", {"todos": True}, format="json")
    assert portal.get("/api/v1/portal/avisos/").json()["nao_lidos"] == 0
    # Equipe confirma o envio manual da mensagem
    assert staff.post(f"/api/v1/portal-admin/mensagens/{msg.pk}/mark-sent/", {}, format="json").json()["status"] == "ENVIADA"



def test_documento_do_checklist_vai_para_o_cadastro(institution, setores, client_for, caso):  # noqa: F811
    cid = caso["cid"]
    p = caso["person"]
    ben = client_for(setores["beneficios"])
    data = ben.get(f"/api/v1/concessoes/{cid}/checklist/").json()
    res = next(i for i in data["itens"] if i["name"] == "Comprovante de residência")
    ide = next(i for i in data["itens"] if i["name"].startswith("Documento de identidade"))
    assert res["person_doc_type"] == "RESIDENCIA" and data["cadastro"]["endereco"] is None

    import json

    f = SimpleUploadedFile("conta.pdf", b"%PDF-1.4 conta de luz", content_type="application/pdf")
    dados = {"cep": "27310-400", "street": "Rua Luiz Ponce", "number": "263", "district": "Centro", "city": "Barra Mansa", "uf": "RJ"}
    r = ben.post(f"/api/v1/concessoes/{cid}/checklist/{res['id']}/attach/", {"file": f, "dados": json.dumps(dados)}, format="multipart")
    assert r.status_code == 200, r.json()
    assert Document.objects.filter(person=p, doc_type="RESIDENCIA", superseded=False).exists()
    addr = Address.objects.get(person=p, valid_to__isnull=True)
    assert addr.street == "Rua Luiz Ponce" and addr.cep == "27310400"

    f = SimpleUploadedFile("rg.pdf", b"%PDF-1.4 rg", content_type="application/pdf")
    r = ben.post(f"/api/v1/concessoes/{cid}/checklist/{ide['id']}/attach/",
                 {"file": f, "dados": json.dumps({"rg_number": "12.345.678-9", "rg_issuer": "DETRAN", "rg_uf": "RJ"})},
                 format="multipart")
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.rg_number == "12.345.678-9" and p.rg_issuer == "DETRAN"
    assert Document.objects.filter(person=p, doc_type="IDENTIDADE").count() == 1
