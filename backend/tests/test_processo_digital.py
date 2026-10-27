"""Processo digital: checklist de documentos por setor, trava de liberação e assinatura com SHA-256."""
import hashlib

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.concessao.models import ChecklistItem, ConcessionStep
from apps.protocolo.models import Attachment, Movement
from tests.conftest import PASSWORD, anexar_checklist
from tests.test_concessao_seguranca import caso  # noqa: F401  (fixture: aposentadoria calculada)

ACK = {"acknowledge_warnings": True, "password": PASSWORD}


def _pdf(text=b"documento"):
    return SimpleUploadedFile("doc.pdf", b"%PDF-1.4 " + text, content_type="application/pdf")


def test_beneficios_so_libera_com_checklist_completo(institution, setores, client_for, caso):  # noqa: F811
    cid = caso["cid"]
    ben = client_for(setores["beneficios"])
    data = ben.get(f"/api/v1/concessoes/{cid}/checklist/").json()
    assert data["setor_atual"] == "BENEFICIOS"
    nomes = {i["name"] for i in data["itens"] if i["sector"] == "BENEFICIOS"}
    assert "Requerimento de aposentadoria assinado pelo servidor" in nomes
    assert "Laudo da junta médica oficial" not in nomes  # só na aposentadoria por incapacidade

    # Sem documentos: não libera
    r = ben.post(f"/api/v1/concessoes/{cid}/send/", ACK, format="json")
    assert r.status_code == 409 and "Checklist de Benefícios incompleto" in r.json()["detail"]

    # Anexa um documento: vai para o Protocolo com o SHA-256 do arquivo
    item = next(i for i in data["itens"] if i["name"].startswith("Requerimento"))
    r = ben.post(f"/api/v1/concessoes/{cid}/checklist/{item['id']}/attach/", {"file": _pdf(b"req")}, format="multipart")
    assert r.status_code == 200
    att = Attachment.objects.get(pk=ChecklistItem.objects.get(pk=item["id"]).attachment_id)
    assert att.sha256 == hashlib.sha256(b"%PDF-1.4 req").hexdigest()

    # "Não se aplica" exige justificativa
    ctc = next(i for i in data["itens"] if i["name"].startswith("Certidão de Tempo"))
    assert ben.post(f"/api/v1/concessoes/{cid}/checklist/{ctc['id']}/waive/", {"note": "não"},
                    format="json").status_code == 409
    assert ben.post(f"/api/v1/concessoes/{cid}/checklist/{ctc['id']}/waive/",
                    {"note": "Servidor sem tempo em outro regime previdenciário."}, format="json").status_code == 200

    # Outro setor não mexe no checklist de Benefícios; o Jurídico não anexa enquanto o processo não chega a ele
    jur = client_for(setores["juridico"])
    assert jur.post(f"/api/v1/concessoes/{cid}/checklist/{item['id']}/reopen/").status_code == 403

    anexar_checklist(ben, cid)
    assert ben.post(f"/api/v1/concessoes/{cid}/send/", {"acknowledge_warnings": True}, format="json").status_code == 409
    r = ben.post(f"/api/v1/concessoes/{cid}/send/", ACK, format="json")
    assert r.status_code == 200 and r.json()["stage"] == "ANALISE_JURIDICA"

    # Assinatura do checklist: hash na trilha e no andamento do Protocolo; relatório de instrução gerado pelo sistema
    step = ConcessionStep.objects.get(concession_id=cid, action="ENVIO_JURIDICO")
    code = step.data["checklist"]["hash_checklist"]
    assert step.signed and len(code) == 64
    assert Movement.objects.filter(process__concessions__pk=cid, text__contains=code).exists()
    rel = ChecklistItem.objects.get(concession_id=cid, system_kind="RELATORIO_INSTRUCAO")
    assert rel.status == "CUMPRIDO" and rel.document_id and len(rel.sha256) == 64

    # Depois de assinado, Benefícios não altera mais (até eventual devolução)
    r = ben.post(f"/api/v1/concessoes/{cid}/checklist/{item['id']}/attach/", {"file": _pdf(b"outro")}, format="multipart")
    assert r.status_code == 409 and "só pode ser alterado" in r.json()["detail"]

    # Parecer favorável gera o parecer em Word e assina o checklist do Jurídico
    r = jur.post(f"/api/v1/concessoes/{cid}/legal/", {"favorable": True, "password": PASSWORD,
                 "text": "Requisitos constitucionais e legais atendidos; fundamentação correta."}, format="json")
    assert r.status_code == 200
    par = ChecklistItem.objects.get(concession_id=cid, system_kind="PARECER_JURIDICO")
    assert par.status == "CUMPRIDO" and par.document_id
    assert ConcessionStep.objects.get(concession_id=cid, action="PARECER_FAVORAVEL").data["checklist"]["hash_checklist"]


def test_modelos_do_checklist_sao_editaveis(institution, master, client_for, caso):  # noqa: F811
    m = client_for(master)
    rows = m.get("/api/v1/concessao-checklist/?concession_kind=APOSENTADORIA&sector=BENEFICIOS").json()
    assert len(rows) >= 8
    r = m.post("/api/v1/concessao-checklist/", {"concession_kind": "APOSENTADORIA", "sector": "BENEFICIOS",
               "name": "Declaração de não acumulação de cargos", "required": True, "source": "ANEXO"}, format="json")
    assert r.status_code == 201, r.json()
    cid = caso["cid"]
    nomes = {i["name"] for i in m.get(f"/api/v1/concessoes/{cid}/checklist/").json()["itens"]}
    assert "Declaração de não acumulação de cargos" in nomes
