"""
Recadastramento (censo) de servidores ativos, aposentados e pensionistas, organizado em CAMPANHAS por ato do órgão.

O segurado atualiza os dados pelo Portal (ou a equipe registra no atendimento presencial). Nada vai para o Cadastro
Único sem conferência: a equipe vê o "antes e depois", aprova (aplica as mudanças, com histórico) ou devolve com o
motivo. Conta bancária e dependentes NÃO são alterados por aqui (exigem documentos próprios): ficam como pendência
para a equipe tratar no Cadastro Único.
"""
from django.conf import settings
from django.db import models

from apps.core.models import InstitutionScopedModel


class Audience(models.TextChoices):
    TODOS = "TODOS", "Servidores ativos, aposentados e pensionistas"
    SERVIDORES = "SERVIDORES", "Só servidores ativos"
    BENEFICIARIOS = "BENEFICIARIOS", "Só aposentados e pensionistas"


class CampaignStatus(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Em preparação"
    ABERTA = "ABERTA", "Aberta"
    ENCERRADA = "ENCERRADA", "Encerrada"


class RegistrationCampaign(InstitutionScopedModel):
    name = models.CharField("nome", max_length=150)
    legal_act = models.CharField("ato que determinou (decreto, portaria, resolução)", max_length=200)
    act_date = models.DateField("data do ato", null=True, blank=True)
    start_date = models.DateField("início")
    end_date = models.DateField("fim (prazo)")
    audience = models.CharField("quem participa", max_length=14, choices=Audience.choices, default=Audience.TODOS)
    organ = models.ForeignKey("cadastros.Organ", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                              verbose_name="só servidores do órgão")
    portal_enabled = models.BooleanField("permitir pelo Portal do Segurado", default=True)
    require_residence_proof = models.BooleanField("exigir comprovante de residência", default=True)
    instructions = models.TextField("orientações", blank=True)
    status = models.CharField("situação", max_length=10, choices=CampaignStatus.choices, default=CampaignStatus.RASCUNHO)
    opened_at = models.DateTimeField("aberta em", null=True, blank=True)
    closed_at = models.DateTimeField("encerrada em", null=True, blank=True)

    class Meta:
        db_table = "registration_campaigns"
        verbose_name = "campanha de recadastramento"
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class Group(models.TextChoices):
    SERVIDOR = "SERVIDOR", "Servidor ativo"
    BENEFICIARIO = "BENEFICIARIO", "Aposentado / pensionista"


class Status(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    ENVIADO = "ENVIADO", "Enviado — aguardando conferência"
    DEVOLVIDO = "DEVOLVIDO", "Devolvido para correção"
    APROVADO = "APROVADO", "Aprovado"


class Channel(models.TextChoices):
    PORTAL = "PORTAL", "Portal do Segurado"
    PRESENCIAL = "PRESENCIAL", "Atendimento presencial"


class Reregistration(InstitutionScopedModel):
    campaign = models.ForeignKey(RegistrationCampaign, on_delete=models.PROTECT, related_name="items",
                                 verbose_name="campanha")
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="reregistrations",
                               verbose_name="segurado")
    group = models.CharField("grupo", max_length=12, choices=Group.choices)
    due_date = models.DateField("prazo")
    status = models.CharField("situação", max_length=10, choices=Status.choices, default=Status.PENDENTE)
    channel = models.CharField("forma", max_length=10, choices=Channel.choices, blank=True)
    submitted_at = models.DateTimeField("enviado em", null=True, blank=True)
    proposed = models.JSONField("dados informados", default=dict, blank=True)
    previous = models.JSONField("dados do cadastro no envio", default=dict, blank=True)
    declarations = models.JSONField("declarações", default=dict, blank=True)
    residence_proof = models.FileField("comprovante de residência", upload_to="recadastramento/%Y/%m/", blank=True)
    id_document = models.FileField("documento de identidade", upload_to="recadastramento/%Y/%m/", blank=True)
    file_hashes = models.JSONField("SHA-256 dos arquivos", default=dict, blank=True)
    review_note = models.TextField("motivo da devolução / observação", blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+", verbose_name="conferido por")
    reviewed_at = models.DateTimeField("conferido em", null=True, blank=True)
    applied = models.JSONField("mudanças aplicadas no Cadastro Único", default=dict, blank=True)
    staff_followup = models.TextField("pendência para a equipe (dependentes, conta…)", blank=True)

    class Meta:
        db_table = "reregistrations"
        verbose_name = "recadastramento"
        ordering = ["due_date", "person__name"]
        constraints = [models.UniqueConstraint(fields=["campaign", "person"], name="uq_reregistration_campaign_person")]
