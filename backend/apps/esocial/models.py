"""
eSocial do RPPS (Fase 6).

Cada evento é gerado como XML no leiaute oficial (versão no parâmetro 'esocial.versao', padrão S_01_03_00) e
guardado aqui com suas PENDÊNCIAS (dados que faltam ou não conferem). O SIST nunca
simula retorno. Com o certificado A1 da instituição cadastrado, a transmissão direta (transmission.py) assina,
envia o lote e consulta o retorno no próprio eSocial. O fluxo é:

  PENDENTE (há pendências) / VALIDADO (pronto) -> EXPORTADO (XML baixado para assinar e transmitir)
  -> ACEITO (recibo informado ou retorno importado) | REJEITADO (erro informado ou retorno importado)

Nada é excluído: corrigir um evento rejeitado ou retificar um aceito gera NOVO evento ligado ao anterior.
"""
from django.conf import settings
from django.db import models

from apps.core.models import InstitutionScopedModel


class EventType(models.TextChoices):
    S1010 = "S-1010", "S-1010 — Tabela de rubricas"
    S1207 = "S-1207", "S-1207 — Benefícios RPPS (remuneração)"
    S1210 = "S-1210", "S-1210 — Pagamentos"
    S1299 = "S-1299", "S-1299 — Fechamento dos eventos periódicos"
    S2400 = "S-2400", "S-2400 — Cadastro do beneficiário"
    S2410 = "S-2410", "S-2410 — Cadastro do benefício (início)"
    S2420 = "S-2420", "S-2420 — Término do benefício"


class EventStatus(models.TextChoices):
    PENDENTE = "PENDENTE", "Com pendências"
    VALIDADO = "VALIDADO", "Validado (pronto para exportar)"
    EXPORTADO = "EXPORTADO", "Exportado ou transmitido (aguardando retorno)"
    ACEITO = "ACEITO", "Aceito pelo eSocial"
    REJEITADO = "REJEITADO", "Rejeitado"
    SUBSTITUIDO = "SUBSTITUIDO", "Substituído por novo evento"


OPEN_STATUSES = {EventStatus.PENDENTE, EventStatus.VALIDADO, EventStatus.EXPORTADO}


class EsocialEvent(InstitutionScopedModel):
    event_type = models.CharField("evento", max_length=6, choices=EventType.choices)
    event_id = models.CharField("Id do evento", max_length=36, unique=True)
    status = models.CharField("situação", max_length=12, choices=EventStatus.choices, default=EventStatus.PENDENTE)
    retification = models.BooleanField("retificação", default=False)
    replaces = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="replaced_by",
                                 verbose_name="substitui / retifica")
    # Origem do evento
    object_type = models.CharField("tipo do objeto", max_length=40)
    object_id = models.CharField("id do objeto", max_length=80)
    reference = models.CharField("referência", max_length=200)
    period = models.CharField("período de apuração", max_length=7, blank=True)
    cpf = models.CharField("CPF do beneficiário", max_length=11, blank=True)
    # Conteúdo
    xml = models.TextField("XML (não assinado)")
    pendencies = models.JSONField("pendências", default=list, blank=True)
    layout_version = models.CharField("versão do leiaute", max_length=12)
    environment = models.PositiveSmallIntegerField("ambiente", choices=[(1, "Produção"), (2, "Produção restrita")])
    # Retorno
    exported_at = models.DateTimeField("exportado em", null=True, blank=True)
    receipt = models.CharField("nº do recibo", max_length=40, blank=True)
    return_code = models.CharField("código de resposta", max_length=10, blank=True)
    return_message = models.TextField("mensagem de retorno", blank=True)
    returned_at = models.DateTimeField("retorno registrado em", null=True, blank=True)

    class Meta:
        db_table = "esocial_events"
        verbose_name = "evento eSocial"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["institution", "event_type", "status"]),
                   models.Index(fields=["institution", "object_type", "object_id"])]

    def __str__(self):
        return f"{self.event_type} — {self.reference}"


class EsocialLog(InstitutionScopedModel):
    """Histórico do evento (geração, validação, exportação, retorno). Somente inclusão."""

    event = models.ForeignKey(EsocialEvent, on_delete=models.PROTECT, related_name="logs", verbose_name="evento")
    action = models.CharField("ação", max_length=20)
    detail = models.TextField("detalhe", blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                             related_name="+", verbose_name="usuário")

    class Meta:
        db_table = "esocial_logs"
        verbose_name = "histórico eSocial"
        ordering = ["-created_at"]


# ================================================================== transmissão direta
class EsocialCertificate(InstitutionScopedModel):
    """
    Certificado digital ICP-Brasil A1 (.pfx) usado para assinar e transmitir. O arquivo e a senha ficam
    CRIPTOGRAFADOS (chave ESOCIAL_CERT_KEY no .env do servidor, fora do banco). Só um ativo por instituição; o
    anterior é desativado (histórico mantido, sem o conteúdo).
    """

    pfx = models.BinaryField("arquivo .pfx (criptografado)", editable=False)
    secret = models.BinaryField("senha (criptografada)", editable=False)
    holder_name = models.CharField("titular", max_length=200)
    holder_doc = models.CharField("CNPJ/CPF do titular", max_length=14)
    subject = models.CharField("assunto", max_length=500)
    issuer = models.CharField("emissor", max_length=500)
    serial = models.CharField("nº de série", max_length=80)
    thumbprint = models.CharField("impressão digital SHA-256", max_length=64)
    valid_from = models.DateTimeField("válido de")
    valid_until = models.DateTimeField("válido até")
    active = models.BooleanField("ativo", default=True)
    last_test_at = models.DateTimeField("último teste de conexão", null=True, blank=True)
    last_test_result = models.CharField("resultado do último teste", max_length=300, blank=True)

    class Meta:
        db_table = "esocial_certificates"
        verbose_name = "certificado do eSocial"
        ordering = ["-created_at"]


class BatchStatus(models.TextChoices):
    RECUSADO = "RECUSADO", "Lote recusado no envio"
    PROCESSANDO = "PROCESSANDO", "Recebido — em processamento"
    PROCESSADO = "PROCESSADO", "Processado (retornos registrados)"


class EsocialBatch(InstitutionScopedModel):
    """Lote enviado ao eSocial (até 50 eventos do mesmo grupo). Guarda o XML assinado enviado e as respostas."""

    environment = models.PositiveSmallIntegerField("ambiente", choices=[(1, "Produção"), (2, "Produção restrita")])
    group = models.PositiveSmallIntegerField("grupo", choices=[(1, "Tabelas"), (2, "Não periódicos"),
                                                               (3, "Periódicos")])
    status = models.CharField("situação", max_length=12, choices=BatchStatus.choices)
    events = models.ManyToManyField(EsocialEvent, related_name="batches", verbose_name="eventos")
    certificate = models.ForeignKey(EsocialCertificate, on_delete=models.PROTECT, related_name="+")
    protocol = models.CharField("protocolo de envio", max_length=60, blank=True)
    sent_at = models.DateTimeField("enviado em")
    response_code = models.CharField("código de resposta", max_length=10, blank=True)
    response_message = models.TextField("mensagem", blank=True)
    request_xml = models.TextField("lote enviado (assinado)")
    request_sha256 = models.CharField("hash do lote", max_length=64)
    response_xml = models.TextField("última resposta", blank=True)
    queried_at = models.DateTimeField("última consulta", null=True, blank=True)
    queries = models.PositiveIntegerField("consultas", default=0)

    class Meta:
        db_table = "esocial_batches"
        verbose_name = "lote do eSocial"
        ordering = ["-sent_at"]
