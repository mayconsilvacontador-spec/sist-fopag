"""
Prova de Vida dos aposentados e pensionistas, organizada em CAMPANHAS.

Cada órgão decide quando fazer (anual, semestral ou extraordinária por decreto/portaria): a campanha guarda o ato
legal, o período, a regra do prazo (fim da campanha ou mês de aniversário), a tolerância antes da suspensão e quem
participa. Nada é fixo no código — serve a qualquer RPPS.
"""
from django.conf import settings
from django.db import models

from apps.core.models import InstitutionScopedModel


class CampaignKind(models.TextChoices):
    ANUAL = "ANUAL", "Anual"
    SEMESTRAL = "SEMESTRAL", "Semestral"
    EXTRAORDINARIA = "EXTRAORDINARIA", "Extraordinária (decreto/portaria)"


class CampaignStatus(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Em preparação"
    ABERTA = "ABERTA", "Aberta"
    ENCERRADA = "ENCERRADA", "Encerrada"


class DeadlineRule(models.TextChoices):
    FIM_CAMPANHA = "FIM_CAMPANHA", "Até o fim da campanha"
    MES_ANIVERSARIO = "MES_ANIVERSARIO", "Até o fim do mês de aniversário (dentro do período)"


class Audience(models.TextChoices):
    TODOS = "TODOS", "Aposentados e pensionistas"
    APOSENTADOS = "APOSENTADOS", "Só aposentados"
    PENSIONISTAS = "PENSIONISTAS", "Só pensionistas"


class LifeProofCampaign(InstitutionScopedModel):
    name = models.CharField("nome", max_length=150)
    kind = models.CharField("tipo", max_length=16, choices=CampaignKind.choices)
    legal_act = models.CharField("ato que determinou (decreto, portaria, resolução)", max_length=200)
    act_date = models.DateField("data do ato", null=True, blank=True)
    start_date = models.DateField("início")
    end_date = models.DateField("fim (prazo)")
    deadline_rule = models.CharField("prazo de cada beneficiário", max_length=16, choices=DeadlineRule.choices,
                                     default=DeadlineRule.FIM_CAMPANHA)
    grace_days = models.PositiveSmallIntegerField("tolerância após o prazo antes da suspensão (dias)", default=30)
    audience = models.CharField("quem participa", max_length=14, choices=Audience.choices, default=Audience.TODOS)
    segment = models.CharField("folha", max_length=20, blank=True, help_text="Vazio = todas as folhas.")
    portal_notice = models.BooleanField("avisar no Portal do Segurado", default=True)
    allow_portal = models.BooleanField("aceitar prova de vida pelo Portal (foto + documento, conferida pela equipe)",
                                       default=True)
    instructions = models.TextField("orientações ao beneficiário", blank=True)
    status = models.CharField("situação", max_length=10, choices=CampaignStatus.choices, default=CampaignStatus.RASCUNHO)
    opened_at = models.DateTimeField("aberta em", null=True, blank=True)
    closed_at = models.DateTimeField("encerrada em", null=True, blank=True)

    class Meta:
        db_table = "life_proof_campaigns"
        verbose_name = "campanha de prova de vida"
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class ProofStatus(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    REALIZADA = "REALIZADA", "Realizada"
    BLOQUEADO = "BLOQUEADO", "Benefício suspenso"
    EM_ANALISE = "EM_ANALISE", "Enviada pelo Portal — em análise"
    DISPENSADA = "DISPENSADA", "Dispensada (justificada)"


class ProofChannel(models.TextChoices):
    PRESENCIAL = "PRESENCIAL", "Presencial no órgão"
    VISITA = "VISITA", "Visita domiciliar / hospitalar"
    PROCURADOR = "PROCURADOR", "Por procurador / curador"
    BANCO = "BANCO", "Na agência bancária (comprovante)"
    PORTAL = "PORTAL", "Pelo Portal do Segurado (validada pela equipe)"
    OUTRO = "OUTRO", "Outro"


class LifeProof(InstitutionScopedModel):
    campaign = models.ForeignKey(LifeProofCampaign, on_delete=models.PROTECT, related_name="proofs",
                                 verbose_name="campanha")
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="life_proofs",
                               verbose_name="beneficiário")
    due_date = models.DateField("prazo")
    status = models.CharField("situação", max_length=12, choices=ProofStatus.choices, default=ProofStatus.PENDENTE)
    done_date = models.DateField("realizada em", null=True, blank=True)
    channel = models.CharField("forma", max_length=12, choices=ProofChannel.choices, blank=True)
    notes = models.TextField("observações / justificativa", blank=True)
    attachment = models.FileField("comprovante", upload_to="provadevida/%Y/%m/", blank=True)
    attachment_sha256 = models.CharField("SHA-256 do comprovante", max_length=64, blank=True)
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="+", verbose_name="registrada por")
    suspended_at = models.DateField("benefício suspenso em", null=True, blank=True)
    suspended_benefits = models.JSONField("benefícios suspensos por esta prova", default=list, blank=True)
    # Prova enviada pelo Portal do Segurado (selfie com documento + foto do documento), conferida pela equipe
    portal_selfie = models.FileField("selfie segurando o documento", upload_to="provadevida/portal/%Y/%m/", blank=True)
    portal_document = models.FileField("foto do documento", upload_to="provadevida/portal/%Y/%m/", blank=True)
    portal_submitted_at = models.DateTimeField("enviada pelo Portal em", null=True, blank=True)
    portal_hashes = models.JSONField("SHA-256 das fotos enviadas", default=dict, blank=True)
    # Vivacidade: fotos tiradas durante os gestos pedidos pela câmera ao vivo (desafios sorteados) e o resultado
    portal_frames = models.JSONField("fotos dos gestos (caminhos no armazenamento)", default=list, blank=True)
    portal_liveness = models.JSONField("verificação de vivacidade (desafios, movimento, aparelho)", default=dict, blank=True)
    status_before_portal = models.CharField("situação antes do envio pelo Portal", max_length=12, blank=True)
    review_note = models.TextField("motivo da recusa (análise da equipe)", blank=True)

    class Meta:
        db_table = "life_proofs"
        verbose_name = "prova de vida"
        ordering = ["due_date", "person__name"]
        constraints = [models.UniqueConstraint(fields=["campaign", "person"], name="uq_life_proof_campaign_person")]
