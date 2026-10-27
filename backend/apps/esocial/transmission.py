"""
Transmissão direta ao eSocial (webservices SOAP com certificado do cliente).

1. O certificado A1 (.pfx) da instituição (ou do procurador) é enviado pela tela e guardado CRIPTOGRAFADO
   (Fernet, chave ESOCIAL_CERT_KEY no .env do servidor). A senha do .pfx também é criptografada.
2. Cada evento VALIDADO é assinado (XMLDSig envelopado, RSA-SHA256, C14N, Reference URI="").
3. Os eventos vão em LOTE (até 50, do mesmo grupo: 1 tabelas, 2 não periódicos, 3 periódicos) para o serviço
   EnviarLoteEventos. Resposta 201 = lote recebido → guarda o protocolo; eventos ficam "aguardando retorno".
4. ConsultarLoteEventos com o protocolo: 101 = ainda processando; 201 = processado → cada evento recebe o recibo
   (aceito) ou as ocorrências (rejeitado), pela mesma rotina da importação manual de retornos.

O ambiente (1 produção / 2 produção restrita) vem do parâmetro 'esocial.ambiente' e precisa ser o mesmo dos
eventos. Nada é simulado: sem certificado ou sem resposta do eSocial, o SIST informa o erro e não muda o evento.
Endereços e namespaces seguem o Manual de Orientação do Desenvolvedor do eSocial (conferir a cada nova versão).
"""
import hashlib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import timezone as dt_tz

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import only_digits

from .models import BatchStatus, EsocialBatch, EsocialCertificate, EsocialEvent, EventStatus

MAX_EVENTS = 50
GROUP_BY_TYPE = {"S-1010": 1, "S-2400": 2, "S-2410": 2, "S-2420": 2, "S-1207": 3, "S-1210": 3, "S-1299": 3}
GROUP_LABEL = {1: "tabelas", 2: "não periódicos", 3: "periódicos"}

URLS = {
    2: {"envio": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/enviarloteeventos/"
                 "WsEnviarLoteEventos.svc",
        "consulta": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/consultarloteeventos/"
                    "WsConsultarLoteEventos.svc"},
    1: {"envio": "https://webservices.envio.esocial.gov.br/servicos/empregador/enviarloteeventos/"
                 "WsEnviarLoteEventos.svc",
        "consulta": "https://webservices.consulta.esocial.gov.br/servicos/empregador/consultarloteeventos/"
                    "WsConsultarLoteEventos.svc"},
}
NS_SEND_WS = "http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/v1_1_0"
NS_SEND_LOTE = "http://www.esocial.gov.br/schema/lote/eventos/envio/v1_1_1"
ACTION_SEND = f"{NS_SEND_WS}/ServicoEnviarLoteEventos/EnviarLoteEventos"
NS_QUERY_WS = "http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/consulta/retornoProcessamento/v1_1_0"
NS_QUERY = "http://www.esocial.gov.br/schema/lote/eventos/envio/consulta/retornoProcessamento/v1_0_0"
ACTION_QUERY = f"{NS_QUERY_WS}/ServicoConsultarLoteEventos/ConsultarLoteEventos"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"


# ================================================================== certificado
def _fernet():
    from cryptography.fernet import Fernet

    key = getattr(settings, "ESOCIAL_CERT_KEY", "")
    if not key:
        raise BusinessRuleError("Chave de criptografia do certificado não configurada no servidor (ESOCIAL_CERT_KEY "
                                "no arquivo .env). Peça ao suporte técnico.")
    return Fernet(key.encode())


def _load_pfx(data: bytes, password: str):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12

    try:
        key, cert, chain = pkcs12.load_key_and_certificates(data, password.encode("utf-8") if password else None)
    except ValueError:
        raise BusinessRuleError("Não foi possível abrir o certificado: senha incorreta ou arquivo não é um .pfx/.p12.")
    if key is None or cert is None:
        raise BusinessRuleError("O arquivo não contém a chave privada e o certificado (use o A1 completo, .pfx).")
    if not isinstance(key, rsa.RSAPrivateKey):
        raise BusinessRuleError("O eSocial exige certificado com chave RSA.")
    return key, cert, list(chain or [])


def _holder(cert) -> tuple[str, str]:
    """Nome e CNPJ/CPF do titular. ICP-Brasil: CN = 'NOME:CNPJ' (e-CNPJ) ou 'NOME:CPF' (e-CPF)."""
    from cryptography.x509.oid import NameOID

    cn = next((a.value for a in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)), "")
    name, _, doc = str(cn).rpartition(":")
    doc = only_digits(doc)
    if len(doc) not in (11, 14):
        m = re.search(r"(\d{14}|\d{11})", str(cn))
        doc, name = (m.group(1), str(cn)) if m else ("", str(cn))
    return (name or str(cn)).strip(), doc


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=dt_tz.utc)


def certificate_info(c: EsocialCertificate | None) -> dict | None:
    if c is None:
        return None
    now = timezone.now()
    return {"id": str(c.pk), "titular": c.holder_name, "documento": c.holder_doc, "emissor": c.issuer,
            "serie": c.serial, "impressao_digital": c.thumbprint, "valido_de": c.valid_from,
            "valido_ate": c.valid_until, "vencido": c.valid_until < now,
            "dias_para_vencer": (c.valid_until - now).days, "enviado_em": c.created_at,
            "enviado_por": c.created_by.full_name if c.created_by else "",
            "ultimo_teste": c.last_test_at, "resultado_teste": c.last_test_result}


def active_certificate(institution) -> EsocialCertificate | None:
    return EsocialCertificate.objects.filter(institution=institution, active=True).select_related("created_by").first()


@transaction.atomic
def install_certificate(institution, data: bytes, password: str, user) -> tuple[EsocialCertificate, list[str]]:
    from cryptography.hazmat.primitives import hashes

    from .builders import Ctx

    if not data or len(data) > 50_000:
        raise BusinessRuleError("Envie o arquivo do certificado A1 (.pfx ou .p12).")
    key, cert, _ = _load_pfx(data, password)
    start, end = _utc(cert.not_valid_before_utc), _utc(cert.not_valid_after_utc)
    if end < timezone.now():
        raise BusinessRuleError(f"Certificado vencido em {timezone.localtime(end):%d/%m/%Y}.")
    name, doc = _holder(cert)
    warnings = []
    nr = Ctx.load(institution).nr_insc
    if len(doc) == 14 and nr and doc[:8] != nr[:8]:
        warnings.append("O CNPJ do certificado é diferente do CNPJ da instituição: só funciona se houver "
                        "procuração eletrônica no eSocial para este CNPJ.")
    if len(doc) == 11:
        warnings.append("Certificado de pessoa física (e-CPF): é preciso procuração eletrônica no eSocial.")
    f = _fernet()
    EsocialCertificate.objects.filter(institution=institution, active=True).update(active=False, pfx=b"", secret=b"")
    c = EsocialCertificate.objects.create(
        institution=institution, pfx=f.encrypt(data), secret=f.encrypt((password or "").encode("utf-8")),
        holder_name=name[:200], holder_doc=doc, subject=cert.subject.rfc4514_string()[:500],
        issuer=cert.issuer.rfc4514_string()[:500], serial=format(cert.serial_number, "X")[:80],
        thumbprint=cert.fingerprint(hashes.SHA256()).hex(), valid_from=start, valid_until=end)
    log_event("UPDATE", module="esocial.transmissao", obj=c, object_repr=f"Certificado do eSocial — {name} ({doc})",
              extra={"valido_ate": end.isoformat(), "impressao_digital": c.thumbprint})
    return c, warnings


@contextmanager
def _material(c: EsocialCertificate):
    """Chave e certificado em memória + arquivos PEM temporários (0600) para o TLS mútuo; apagados ao sair."""
    from cryptography.hazmat.primitives import serialization

    f = _fernet()
    try:
        data, password = f.decrypt(bytes(c.pfx)), f.decrypt(bytes(c.secret)).decode("utf-8")
    except Exception:
        raise BusinessRuleError("Não foi possível abrir o certificado guardado (a chave do servidor mudou?). "
                                "Envie o certificado de novo.")
    key, cert, chain = _load_pfx(data, password)
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    with tempfile.TemporaryDirectory(prefix="esocial-") as tmp:
        kp, cp = os.path.join(tmp, "k.pem"), os.path.join(tmp, "c.pem")
        for path, content in ((kp, key_pem), (cp, cert_pem + b"".join(
                x.public_bytes(serialization.Encoding.PEM) for x in chain))):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
        yield {"key": key_pem, "cert": cert_pem, "files": (cp, kp)}


def _require_valid(institution) -> EsocialCertificate:
    c = active_certificate(institution)
    if c is None:
        raise BusinessRuleError("Nenhum certificado digital cadastrado. Envie o certificado A1 em eSocial › Transmissão.")
    if c.valid_until < timezone.now():
        raise BusinessRuleError("O certificado digital está vencido. Envie o certificado renovado.")
    return c


# ================================================================== assinatura e SOAP
DS = "http://www.w3.org/2000/09/xmldsig#"


def sign_event(xml: str, key_pem: bytes, cert_pem: bytes) -> str:
    """
    Assinatura XMLDSig envelopada exigida pelo eSocial: <Signature xmlns="..."> (sem prefixo "ds:") como último
    filho do <eSocial>, Reference URI="", transforms enveloped-signature + C14N, digest SHA-256, RSA-SHA256 e o
    certificado em KeyInfo. Feita direto (lxml + cryptography) porque o modo sem prefixo do signxml gera assinatura
    inválida; a conferência nos testes usa o verificador do signxml.
    """
    import base64

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.x509 import load_pem_x509_certificate
    from lxml import etree

    root = etree.fromstring(xml.encode("utf-8"), parser=etree.XMLParser(remove_blank_text=True))
    if any(etree.QName(n).localname == "Signature" for n in root):
        raise BusinessRuleError("Evento já assinado.")
    digest = base64.b64encode(hashlib.sha256(etree.tostring(root, method="c14n")).digest()).decode()
    q = lambda tag: f"{{{DS}}}{tag}"  # noqa: E731
    sig = etree.SubElement(root, q("Signature"), nsmap={None: DS})
    si = etree.SubElement(sig, q("SignedInfo"))
    etree.SubElement(si, q("CanonicalizationMethod"), Algorithm=C14N)
    etree.SubElement(si, q("SignatureMethod"), Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")
    ref = etree.SubElement(si, q("Reference"), URI="")
    tr = etree.SubElement(ref, q("Transforms"))
    etree.SubElement(tr, q("Transform"), Algorithm=f"{DS}enveloped-signature")
    etree.SubElement(tr, q("Transform"), Algorithm=C14N)
    etree.SubElement(ref, q("DigestMethod"), Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
    etree.SubElement(ref, q("DigestValue")).text = digest
    key = serialization.load_pem_private_key(key_pem, password=None)
    value = key.sign(etree.tostring(si, method="c14n"), padding.PKCS1v15(), hashes.SHA256())
    etree.SubElement(sig, q("SignatureValue")).text = base64.b64encode(value).decode()
    der = load_pem_x509_certificate(cert_pem).public_bytes(serialization.Encoding.DER)
    x509 = etree.SubElement(etree.SubElement(sig, q("KeyInfo")), q("X509Data"))
    etree.SubElement(x509, q("X509Certificate")).text = base64.b64encode(der).decode()
    return etree.tostring(root, encoding="unicode")


def _lote(nr_insc: str, transmitter_doc: str, group: int, signed: list[tuple[str, str]]) -> str:
    evs = "".join(f'<evento Id="{eid}">{x}</evento>' for eid, x in signed)
    tp_trans = "1" if len(transmitter_doc) == 14 else "2"
    return (f'<eSocial xmlns="{NS_SEND_LOTE}"><envioLoteEventos grupo="{group}">'
            f"<ideEmpregador><tpInsc>1</tpInsc><nrInsc>{nr_insc}</nrInsc></ideEmpregador>"
            f"<ideTransmissor><tpInsc>{tp_trans}</tpInsc><nrInsc>{transmitter_doc}</nrInsc></ideTransmissor>"
            f"<eventos>{evs}</eventos></envioLoteEventos></eSocial>")


def _soap(ws_ns: str, operation: str, wrapper: str, content: str) -> str:
    return ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:v1="{ws_ns}"><soapenv:Header/><soapenv:Body><v1:{operation}><v1:{wrapper}>{content}'
            f"</v1:{wrapper}></v1:{operation}></soapenv:Body></soapenv:Envelope>")


def _post(url: str, action: str, body: str, files) -> str:
    import requests

    try:
        r = requests.post(url, data=body.encode("utf-8"), cert=files, timeout=90,
                          headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": action})
    except requests.exceptions.SSLError as e:
        raise BusinessRuleError(f"Conexão segura com o eSocial recusada (certificado?): {str(e)[:200]}")
    except requests.exceptions.RequestException as e:
        raise BusinessRuleError(f"Sem comunicação com o eSocial: {type(e).__name__}. Tente de novo mais tarde.")
    if r.status_code == 403:
        raise BusinessRuleError("O eSocial recusou o certificado (acesso proibido). Confira se é ICP-Brasil A1 válido "
                                "e se há procuração para este CNPJ.")
    if r.status_code >= 400 and "Envelope" not in r.text:
        raise BusinessRuleError(f"O eSocial respondeu com erro HTTP {r.status_code}.")
    return r.text


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(root, name: str) -> str:
    for n in root.iter():
        if _local(n.tag) == name and n.text:
            return n.text.strip()
    return ""


def _occurrences(root) -> list[str]:
    out = []
    for n in root.iter():
        if _local(n.tag) == "ocorrencia":
            parts = {_local(x.tag): (x.text or "").strip() for x in n}
            out.append(f"{parts.get('codigo', '')} {parts.get('descricao', '')}".strip())
    return out


def _parse(text: str):
    try:
        return ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        raise BusinessRuleError("Resposta do eSocial em formato inesperado.")


# ================================================================== operações
def test_connection(institution) -> dict:
    """Apresenta o certificado ao serviço de consulta (sem enviar evento). 200 = certificado aceito."""
    import requests

    c = _require_valid(institution)
    from .builders import Ctx

    env = Ctx.load(institution).environment
    with _material(c) as m:
        try:
            r = requests.get(URLS[env]["consulta"] + "?wsdl", cert=m["files"], timeout=30)
            ok, msg = r.status_code == 200, (
                "Certificado aceito pelo eSocial — conexão pronta para transmitir." if r.status_code == 200 else
                "O eSocial recusou o certificado (acesso proibido)." if r.status_code == 403 else
                f"O eSocial respondeu HTTP {r.status_code}.")
        except requests.exceptions.RequestException as e:
            ok, msg = False, f"Sem comunicação com o eSocial: {type(e).__name__}."
    c.last_test_at, c.last_test_result = timezone.now(), msg[:300]
    c.save(update_fields=["last_test_at", "last_test_result", "updated_at"])
    return {"ok": ok, "mensagem": msg, "ambiente": "Produção" if env == 1 else "Produção restrita (testes)"}


def transmit(institution, events: list[EsocialEvent], user) -> EsocialBatch:
    from .builders import Ctx
    from .services import _log

    if not events:
        raise BusinessRuleError("Selecione os eventos.")
    if len(events) > MAX_EVENTS:
        raise BusinessRuleError(f"Um lote aceita até {MAX_EVENTS} eventos.")
    bad = [e for e in events if e.status != EventStatus.VALIDADO]
    if bad:
        raise BusinessRuleError(f"{len(bad)} evento(s) não estão validados (com pendência, já enviados ou finalizados).")
    groups = {GROUP_BY_TYPE[e.event_type] for e in events}
    if len(groups) > 1:
        raise BusinessRuleError("Um lote só pode ter eventos do mesmo grupo (tabelas, não periódicos ou periódicos).")
    ctx = Ctx.load(institution)
    if any(e.environment != ctx.environment for e in events):
        raise BusinessRuleError("Há eventos gerados para outro ambiente do eSocial. Revalide-os antes de enviar.")
    if not ctx.nr_insc:
        raise BusinessRuleError("CNPJ da instituição não informado.")
    c = _require_valid(institution)
    group = groups.pop()
    with _material(c) as m:
        signed = [(e.event_id, sign_event(e.xml, m["key"], m["cert"])) for e in events]
        lote = _lote(ctx.nr_insc, c.holder_doc or ctx.nr_insc, group, signed)
        text = _post(URLS[ctx.environment]["envio"], ACTION_SEND, _soap(NS_SEND_WS, "EnviarLoteEventos",
                                                                         "loteEventos", lote), m["files"])
    root = _parse(text)
    code, desc, protocol = _first(root, "cdResposta"), _first(root, "descResposta"), _first(root, "protocoloEnvio")
    msg = "; ".join([desc] + _occurrences(root)).strip("; ")
    ok = code == "201" and bool(protocol)
    with transaction.atomic():
        b = EsocialBatch.objects.create(
            institution=institution, environment=ctx.environment, group=group, certificate=c,
            status=BatchStatus.PROCESSANDO if ok else BatchStatus.RECUSADO, protocol=protocol,
            sent_at=timezone.now(), response_code=code, response_message=msg[:4000], request_xml=lote,
            request_sha256=hashlib.sha256(lote.encode("utf-8")).hexdigest(), response_xml=text[:200000])
        b.events.set(events)
        for e in events:
            if ok:
                e.status, e.exported_at = EventStatus.EXPORTADO, timezone.now()
                e.save(update_fields=["status", "exported_at", "updated_at"])
                _log(e, "TRANSMITIDO", f"Lote protocolo {protocol}", user)
            else:
                _log(e, "ENVIO_RECUSADO", f"{code} {msg}"[:2000], user)
        log_event("EXPORT", module="esocial.transmissao", obj=b,
                  object_repr=f"Lote eSocial ({GROUP_LABEL[group]}, {len(events)} evento(s)) — "
                              f"{'recebido, protocolo ' + protocol if ok else 'recusado: ' + code}",
                  extra={"protocolo": protocol, "codigo": code, "sha256": b.request_sha256})
    return b


def query(batch: EsocialBatch, user) -> EsocialBatch:
    """Consulta o processamento do lote e registra o retorno de cada evento (aceito com recibo ou rejeitado)."""
    from .services import apply_returns

    if batch.status != BatchStatus.PROCESSANDO or not batch.protocol:
        raise BusinessRuleError("Só lotes recebidos e em processamento podem ser consultados.")
    c = _require_valid(batch.institution)
    body = (f'<eSocial xmlns="{NS_QUERY}"><consultaLoteEventos><protocoloEnvio>{batch.protocol}</protocoloEnvio>'
            "</consultaLoteEventos></eSocial>")
    with _material(c) as m:
        text = _post(URLS[batch.environment]["consulta"], ACTION_QUERY,
                     _soap(NS_QUERY_WS, "ConsultarLoteEventos", "consulta", body), m["files"])
    root = _parse(text)
    code, desc = _first(root, "cdResposta"), _first(root, "descResposta")
    with transaction.atomic():
        batch.queried_at, batch.queries = timezone.now(), batch.queries + 1
        batch.response_xml, batch.response_code = text[:200000], code
        batch.response_message = "; ".join([desc] + _occurrences(root)).strip("; ")[:4000]
        if code == "201":
            apply_returns(batch.institution, root, user)
            batch.status = BatchStatus.PROCESSADO
        elif code and not code.startswith("1"):
            # Lote com erro no processamento: os eventos não foram processados e podem ser enviados de novo
            from .services import _log

            batch.status = BatchStatus.RECUSADO
            for e in batch.events.filter(status=EventStatus.EXPORTADO):
                e.status = EventStatus.VALIDADO
                e.save(update_fields=["status", "updated_at"])
                _log(e, "LOTE_COM_ERRO", f"{code} {batch.response_message}"[:2000], user)
        batch.save()
    return batch
