"""
Transmissão direta ao eSocial: certificado A1 criptografado, assinatura XMLDSig verificável, lote, protocolo e
retorno. O webservice do governo é SUBSTITUÍDO NO TESTE (monkeypatch em requests.post) — no sistema real nada é
simulado: a resposta vem do eSocial.
"""
from datetime import datetime, timedelta, timezone as tz

import pytest
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from apps.esocial import transmission as tx
from apps.esocial.models import BatchStatus, EsocialCertificate, EsocialEvent

from .conftest import PASSWORD

CNPJ = "11222333000181"
URL = "/api/v1/esocial"


def _pfx(password=b"senha-do-pfx", days=365):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"INSTITUTO DE TESTE:{CNPJ}")])
    now = datetime.now(tz.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=days)).sign(key, hashes.SHA256()))
    data = pkcs12.serialize_key_and_certificates(b"teste", key, cert, None,
                                                 serialization.BestAvailableEncryption(password))
    return data, cert


def _event(inst, n=1):
    eid = f"ID1{CNPJ}20261020120000{n:05d}"
    xml = (f'<eSocial xmlns="http://www.esocial.gov.br/schema/evt/evtCdBenefIn/v_S_01_03_00">'
           f'<evtCdBenefIn Id="{eid}"><ideEvento><tpAmb>2</tpAmb></ideEvento></evtCdBenefIn></eSocial>')
    return EsocialEvent.objects.create(institution=inst, event_type="S-2400", event_id=eid, status="VALIDADO",
                                       object_type="people.person", object_id=str(n), reference=f"Pessoa {n}",
                                       xml=xml, layout_version="S_01_03_00", environment=2)


class FakeResponse:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


ENVIO_OK = """<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><EnviarLoteEventosResponse>
<EnviarLoteEventosResult><eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/retornoEnvio/v1_1_0">
<retornoEnvioLoteEventos><status><cdResposta>201</cdResposta><descResposta>Lote Recebido com Sucesso.</descResposta>
</status><dadosRecepcaoLote><protocoloEnvio>1.2.202610.0000000000000000001</protocoloEnvio></dadosRecepcaoLote>
</retornoEnvioLoteEventos></eSocial></EnviarLoteEventosResult></EnviarLoteEventosResponse></s:Body></s:Envelope>"""

CONSULTA_OK = """<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><ConsultarLoteEventosResponse>
<ConsultarLoteEventosResult><eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/retornoProcessamento/v1_3_0">
<retornoProcessamentoLoteEventos><status><cdResposta>201</cdResposta><descResposta>Lote processado</descResposta></status>
<retornoEventos>
 <evento Id="{ok}"><retornoEvento><eSocial xmlns="http://www.esocial.gov.br/schema/evt/retornoEvento/v1_2_1">
  <retornoEvento Id="ID9"><processamento><cdResposta>201</cdResposta><descResposta>Sucesso.</descResposta></processamento>
  <recibo><nrRecibo>1.2.0000000000000000099</nrRecibo></recibo></retornoEvento></eSocial></retornoEvento></evento>
 <evento Id="{bad}"><retornoEvento><eSocial xmlns="http://www.esocial.gov.br/schema/evt/retornoEvento/v1_2_1">
  <retornoEvento Id="ID8"><processamento><cdResposta>401</cdResposta><descResposta>Erro</descResposta>
  <ocorrencias><ocorrencia><codigo>1234</codigo><descricao>CPF inexistente</descricao></ocorrencia></ocorrencias>
  </processamento></retornoEvento></eSocial></retornoEvento></evento>
</retornoEventos></retornoProcessamentoLoteEventos></eSocial></ConsultarLoteEventosResult>
</ConsultarLoteEventosResponse></s:Body></s:Envelope>"""


@pytest.fixture
def chave(settings):
    settings.ESOCIAL_CERT_KEY = Fernet.generate_key().decode()


@pytest.fixture
def com_cnpj(institution):
    institution.cnpj = CNPJ
    institution.save()
    return institution


def test_certificado_assinatura_e_lote(com_cnpj, master, consulta, client_for, chave, monkeypatch):
    inst = com_cnpj
    c = client_for(master)
    data, cert = _pfx()
    up = lambda **kw: c.post(f"{URL}/transmissao/certificado/", {"arquivo": _file(data), **kw}, format="multipart")  # noqa
    assert up(senha_certificado="senha-do-pfx", password="errada-123").status_code == 409  # sem a senha do usuário
    assert up(senha_certificado="outra", password=PASSWORD).status_code == 409  # senha do .pfx errada
    r = up(senha_certificado="senha-do-pfx", password=PASSWORD)
    assert r.status_code == 201, r.json()
    assert r.json()["certificado"]["documento"] == CNPJ and r.json()["avisos"] == []
    stored = EsocialCertificate.objects.get(institution=inst, active=True)
    assert data not in bytes(stored.pfx)  # guardado criptografado
    cc = client_for(consulta)  # Consulta vê, mas não instala certificado nem transmite
    assert cc.post(f"{URL}/transmissao/certificado/", {"arquivo": _file(data), "password": PASSWORD},
                   format="multipart").status_code == 403
    assert cc.post(f"{URL}/transmissao/transmitir/", {"ids": [], "password": PASSWORD}, format="json").status_code == 403

    # Assinatura verificável com o próprio certificado (RSA-SHA256, sem prefixo ds:)
    e1, e2 = _event(inst, 1), _event(inst, 2)
    with tx._material(stored) as m:
        signed = tx.sign_event(e1.xml, m["key"], m["cert"])
    assert "<Signature xmlns=" in signed and "rsa-sha256" in signed
    _verify(signed, cert)

    sent = {}

    def fake_post(url, data, cert, timeout, headers):
        sent.setdefault("calls", []).append((url, headers["SOAPAction"], data.decode()))
        return FakeResponse(ENVIO_OK if "Enviar" in headers["SOAPAction"]
                            else CONSULTA_OK.format(ok=e1.event_id, bad=e2.event_id))

    monkeypatch.setattr("requests.post", fake_post)
    tr = f"{URL}/transmissao/transmitir/"
    assert c.post(tr, {"ids": [str(e1.pk)], "password": "errada-123"}, format="json").status_code == 409
    r = c.post(tr, {"ids": [str(e1.pk), str(e2.pk)], "password": PASSWORD}, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["status"] == "PROCESSANDO" and r.json()["protocol"].startswith("1.2.")
    url, action, body = sent["calls"][0]
    assert "producaorestrita" in url and action.endswith("EnviarLoteEventos")
    assert 'grupo="2"' in body and f"<nrInsc>{CNPJ}</nrInsc>" in body and body.count("<Signature xmlns=") == 2
    e1.refresh_from_db()
    assert e1.status == "EXPORTADO"
    # Reenviar evento já enviado é recusado
    assert c.post(tr, {"ids": [str(e1.pk)], "password": PASSWORD}, format="json").status_code == 409

    bid = r.json()["id"]
    r = c.post(f"{URL}/lotes/{bid}/consultar/")
    assert r.status_code == 200, r.json()
    assert r.json()["status"] == BatchStatus.PROCESSADO
    e1.refresh_from_db()
    e2.refresh_from_db()
    assert e1.status == "ACEITO" and e1.receipt == "1.2.0000000000000000099"
    assert e2.status == "REJEITADO" and "CPF inexistente" in e2.return_message


def test_lote_recusado_e_certificado_ausente(com_cnpj, master, client_for, chave, monkeypatch):
    c = client_for(master)
    ev = _event(com_cnpj, 3)
    r = c.post(f"{URL}/transmissao/transmitir/", {"ids": [str(ev.pk)], "password": PASSWORD}, format="json")
    assert r.status_code == 409 and "certificado" in r.json()["detail"].lower()
    data, _ = _pfx()
    assert c.post(f"{URL}/transmissao/certificado/", {"arquivo": _file(data), "senha_certificado": "senha-do-pfx",
                                                      "password": PASSWORD}, format="multipart").status_code == 201
    monkeypatch.setattr("requests.post", lambda *a, **k: FakeResponse(
        ENVIO_OK.replace("<cdResposta>201", "<cdResposta>402").replace("1.2.202610.0000000000000000001", "")))
    r = c.post(f"{URL}/transmissao/transmitir/", {"ids": [str(ev.pk)], "password": PASSWORD}, format="json")
    assert r.status_code == 201 and r.json()["status"] == "RECUSADO"
    ev.refresh_from_db()
    assert ev.status == "VALIDADO"  # continua pronto para novo envio


def _file(data):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("cert.pfx", data, content_type="application/x-pkcs12")


def _verify(signed: str, cert):
    """Conferência pelo padrão XMLDSig: resumo do documento sem a assinatura (C14N) e RSA-SHA256 do SignedInfo."""
    import base64
    import hashlib

    from cryptography.hazmat.primitives.asymmetric import padding
    from lxml import etree

    ds = "{http://www.w3.org/2000/09/xmldsig#}"
    root = etree.fromstring(signed.encode())
    sig = root.find(f"{ds}Signature")
    assert sig is not None and sig.prefix is None and root[-1] is sig
    si = sig.find(f"{ds}SignedInfo")
    assert si.find(f"{ds}Reference").get("URI") == ""
    si_c14n = etree.tostring(si, method="c14n")
    value = base64.b64decode(sig.findtext(f"{ds}SignatureValue"))
    cert.public_key().verify(value, si_c14n, padding.PKCS1v15(), hashes.SHA256())  # lança se inválida
    expected = si.findtext(f"{ds}Reference/{ds}DigestValue")
    root.remove(sig)
    assert base64.b64encode(hashlib.sha256(etree.tostring(root, method="c14n")).digest()).decode() == expected
    # certificado em KeyInfo é o do titular
    der = base64.b64decode(sig.findtext(f"{ds}KeyInfo/{ds}X509Data/{ds}X509Certificate"))
    assert der == cert.public_bytes(serialization.Encoding.DER)
