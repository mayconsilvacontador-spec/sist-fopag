"""Sobrestamento (pausa) e desistência do requerimento de aposentadoria."""
import io
from datetime import timedelta

from django.utils import timezone

from apps.alerts.models import Alert
from apps.concessao.models import Concession, ConcessionStep
from apps.employment.models import EmploymentLink
from apps.protocolo.models import Movement, Process
from tests.conftest import PASSWORD, enviar
from tests.test_concessao_seguranca import caso  # noqa: F401  (fixture: concessão calculada)

MOTIVO = "Servidor pediu prazo para decidir sobre a aposentadoria."


def test_sobrestar_e_retomar(institution, setores, client_for, caso):  # noqa: F811
    cid = caso["cid"]
    ben = client_for(setores["beneficios"])
    until = (timezone.localdate() + timedelta(days=30)).isoformat()
    assert ben.post(f"/api/v1/concessoes/{cid}/suspend/", {"reason": MOTIVO, "until": until},
                    format="json").status_code == 409  # sem senha
    r = ben.post(f"/api/v1/concessoes/{cid}/suspend/", {"reason": MOTIVO, "until": until, "password": PASSWORD},
                 format="json")
    assert r.status_code == 200 and r.json()["stage"] == "SOBRESTADO" and r.json()["suspended_from"] == "CALCULADO"
    c = Concession.objects.get(pk=cid)
    assert c.process.status == "SOBRESTADO"
    assert Alert.objects.filter(institution=institution, code="CONCESSAO_PENDENTE", title__startswith="Processo sobrestado",
                                status="ABERTO").exists()
    # Pausado: nenhum ato do fluxo anda
    assert enviar(ben, cid).status_code == 409
    assert ben.post(f"/api/v1/concessoes/{cid}/calculate/").status_code == 409

    r = ben.post(f"/api/v1/concessoes/{cid}/resume/", {"text": "Servidor confirmou o pedido.", "password": PASSWORD},
                 format="json")
    assert r.status_code == 200 and r.json()["stage"] == "CALCULADO"
    assert Process.objects.get(pk=c.process_id).status == "EM_TRAMITACAO"
    assert set(ConcessionStep.objects.filter(concession_id=cid).values_list("action", flat=True)) >= {"SOBRESTAMENTO", "RETOMADA"}
    assert Movement.objects.filter(process_id=c.process_id, kind="RETOMADA").exists()


def test_desistencia_arquiva_sem_conceder(institution, setores, client_for, caso):  # noqa: F811
    cid = caso["cid"]
    ben = client_for(setores["beneficios"])
    assert enviar(ben, cid).status_code == 200  # já no Jurídico
    body = {"reason": "Servidor desistiu de se aposentar neste momento.", "password": PASSWORD}
    r = ben.post(f"/api/v1/concessoes/{cid}/withdraw/", body, format="json")
    assert r.status_code == 409 and "pedido de desistência" in r.json()["detail"]
    r = ben.post(f"/api/v1/concessoes/{cid}/withdraw/", {**body, "request_attached": True}, format="json")
    assert r.status_code == 200 and r.json()["stage"] == "DESISTENCIA"
    c = Concession.objects.get(pk=cid)
    assert c.process.status == "ARQUIVADO" and c.benefits.count() == 0
    assert EmploymentLink.objects.get(pk=c.link_id).status == "ATIVO"
    docs = ben.get(f"/api/v1/concessoes/{cid}/documents/").json()
    assert docs[0]["kind"] == "TERMO_DESISTENCIA"
    from docx import Document

    content = ben.get(f"/api/v1/concessoes/{cid}/documents/{docs[0]['id']}/download/").content
    text = "\n".join(p.text for p in Document(io.BytesIO(content)).paragraphs)
    assert "DESISTÊNCIA" in text and "Servidor desistiu" in text
    # Arquivado: não volta ao fluxo
    assert ben.post(f"/api/v1/concessoes/{cid}/resume/", {"text": "Retomar processo", "password": PASSWORD},
                    format="json").status_code == 409


def test_desistencia_apos_assinatura_e_recusada(institution, setores, client_for, caso):  # noqa: F811
    cid = caso["cid"]
    Concession.objects.filter(pk=cid).update(stage="ATO_EMITIDO")
    r = client_for(setores["beneficios"]).post(
        f"/api/v1/concessoes/{cid}/withdraw/",
        {"reason": "Servidor desistiu de se aposentar.", "request_attached": True, "password": PASSWORD}, format="json")
    assert r.status_code == 409 and "antes da assinatura" in r.json()["detail"]
