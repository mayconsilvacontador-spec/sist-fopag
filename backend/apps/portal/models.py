"""
Portal do Segurado (Fase 8).

O acesso é criado pela equipe do RPPS para uma pessoa do Cadastro Único (aposentado, pensionista ou servidor):
gera-se um usuário marcado `is_portal`, com senha provisória entregue ao segurado (troca obrigatória no primeiro
acesso). O usuário do portal NUNCA acessa as telas internas — o ModulePermission recusa qualquer rota que não seja
do portal — e todas as consultas do portal são filtradas pela pessoa vinculada ao acesso.
"""
from django.conf import settings
from django.db import models

from apps.core.models import InstitutionScopedModel


class PortalAccess(InstitutionScopedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="portal_access",
                                verbose_name="usuário")
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="portal_accesses",
                               verbose_name="segurado")
    active = models.BooleanField("ativo", default=True)
    last_access = models.DateTimeField("último acesso", null=True, blank=True)

    class Meta:
        db_table = "portal_accesses"
        verbose_name = "acesso ao portal"
        ordering = ["person__name"]
        constraints = [models.UniqueConstraint(fields=["institution", "person"], name="uq_portal_person")]


class RequestKind(models.TextChoices):
    ATUALIZACAO = "ATUALIZACAO", "Atualização cadastral (endereço, telefone, e-mail, conta)"
    REQUERIMENTO = "REQUERIMENTO", "Requerimento (certidão, revisão, outros)"
    DUVIDA = "DUVIDA", "Dúvida / atendimento"


class RequestStatus(models.TextChoices):
    ABERTA = "ABERTA", "Recebida"
    EM_ANALISE = "EM_ANALISE", "Em análise"
    RESPONDIDA = "RESPONDIDA", "Respondida"


class PortalRequest(InstitutionScopedModel):
    """Solicitação feita pelo segurado no portal. A equipe responde (e, se preciso, abre processo no Protocolo)."""

    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="portal_requests",
                               verbose_name="segurado")
    kind = models.CharField("tipo", max_length=12, choices=RequestKind.choices)
    subject = models.CharField("assunto", max_length=150)
    message = models.TextField("mensagem")
    status = models.CharField("situação", max_length=10, choices=RequestStatus.choices, default=RequestStatus.ABERTA)
    answer = models.TextField("resposta", blank=True)
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+", verbose_name="respondida por")
    answered_at = models.DateTimeField("respondida em", null=True, blank=True)
    process = models.ForeignKey("protocolo.Process", on_delete=models.PROTECT, null=True, blank=True,
                                related_name="+", verbose_name="processo aberto")

    class Meta:
        db_table = "portal_requests"
        verbose_name = "solicitação do portal"
        ordering = ["-created_at"]


class NoticeLevel(models.TextChoices):
    INFO = "INFO", "Informação"
    ATENCAO = "ATENCAO", "Atenção"
    URGENTE = "URGENTE", "Urgente"


class PortalNotification(InstitutionScopedModel):
    """Aviso para o segurado (aparece no sininho do Portal). `key` evita repetir o mesmo aviso."""

    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="portal_notifications",
                               verbose_name="segurado")
    key = models.CharField("chave", max_length=120)
    level = models.CharField("nível", max_length=8, choices=NoticeLevel.choices, default=NoticeLevel.INFO)
    title = models.CharField("título", max_length=150)
    message = models.TextField("mensagem")
    tab = models.CharField("tela do portal", max_length=30, blank=True,
                           help_text="Aba do portal que o aviso abre (ex.: prova-de-vida, contracheques).")
    read_at = models.DateTimeField("lido em", null=True, blank=True)

    class Meta:
        db_table = "portal_notifications"
        verbose_name = "aviso do portal"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["person", "key"], name="uq_portal_notification_key")]


class MessageChannel(models.TextChoices):
    WHATSAPP = "WHATSAPP", "WhatsApp"
    SMS = "SMS", "SMS"


class MessageStatus(models.TextChoices):
    PENDENTE = "PENDENTE", "Aguardando envio"
    ENVIADA = "ENVIADA", "Enviada"
    FALHA = "FALHA", "Falha no envio"
    CANCELADA = "CANCELADA", "Cancelada"


class OutboundMessage(InstitutionScopedModel):
    """
    Mensagem para o celular do segurado. Envio automático só com provedor contratado (SMS/WhatsApp Business) —
    o sistema NUNCA marca como enviada sem confirmação. Sem provedor, a equipe envia pelo WhatsApp com um clique
    (link com o texto pronto) e confirma o envio.
    """

    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="outbound_messages",
                               verbose_name="destinatário")
    notification = models.ForeignKey(PortalNotification, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="messages", verbose_name="aviso")
    channel = models.CharField("canal", max_length=10, choices=MessageChannel.choices, default=MessageChannel.WHATSAPP)
    phone = models.CharField("celular", max_length=20)
    text = models.TextField("texto")
    status = models.CharField("situação", max_length=10, choices=MessageStatus.choices, default=MessageStatus.PENDENTE)
    sent_at = models.DateTimeField("enviada em", null=True, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                related_name="+", verbose_name="enviada por")
    provider_response = models.TextField("retorno do provedor / observação", blank=True)

    class Meta:
        db_table = "portal_outbound_messages"
        verbose_name = "mensagem ao celular"
        ordering = ["-created_at"]
