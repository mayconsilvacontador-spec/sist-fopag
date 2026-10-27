"""
Protocolo: abertura de processos, tramitação entre setores e prazos.

Serve a qualquer tipo de órgão (RPPS, Prefeitura, Autarquia, Fundo) e a
qualquer assunto. Os processos de concessão (Fase 4) nascerão aqui.

A tramitação é um histórico imutável (Movement): cada envio, recebimento,
sobrestamento, arquivamento etc. vira um registro novo.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel


class Sector(InstitutionScopedModel):
    name = models.CharField("nome", max_length=120)
    code = models.CharField("sigla", max_length=20)
    organ = models.ForeignKey("cadastros.Organ", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                              verbose_name="órgão")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="protocol_sectors", blank=True,
                                     verbose_name="servidores do setor")
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "protocol_sectors"
        verbose_name = "setor"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="uq_sector_code")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProcessType(InstitutionScopedModel):
    """Assunto/tipo de processo, com o prazo padrão para conclusão."""

    name = models.CharField("nome", max_length=120)
    deadline_days = models.PositiveSmallIntegerField("prazo para conclusão (dias)", default=30)
    business_days = models.BooleanField("prazo em dias úteis", default=True)
    sector_deadline_days = models.PositiveSmallIntegerField(
        "prazo por setor (dias)", null=True, blank=True,
        help_text="Prazo padrão para cada setor despachar. Vazio = sem prazo por setor.",
    )
    description = models.TextField("descrição / documentos exigidos", blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "protocol_process_types"
        verbose_name = "tipo de processo"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["institution", "name"], name="uq_process_type_name")]

    def __str__(self):
        return self.name


class HolidayKind(models.TextChoices):
    NACIONAL = "NACIONAL", "Nacional"
    ESTADUAL = "ESTADUAL", "Estadual"
    MUNICIPAL = "MUNICIPAL", "Municipal"
    PONTO_FACULTATIVO = "PONTO_FACULTATIVO", "Ponto facultativo"


class Holiday(InstitutionScopedModel):
    """Dia não útil para contagem de prazos."""

    date = models.DateField("data")
    name = models.CharField("descrição", max_length=120)
    kind = models.CharField("tipo", max_length=20, choices=HolidayKind.choices)
    active = models.BooleanField("considerar na contagem", default=True)

    class Meta:
        db_table = "protocol_holidays"
        verbose_name = "feriado"
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["institution", "date"], name="uq_holiday_date")]

    def __str__(self):
        return f"{self.date:%d/%m/%Y} - {self.name}"


class ProcessStatus(models.TextChoices):
    EM_TRAMITACAO = "EM_TRAMITACAO", "Em tramitação"
    SOBRESTADO = "SOBRESTADO", "Sobrestado"
    ARQUIVADO = "ARQUIVADO", "Arquivado"
    CONCLUIDO = "CONCLUIDO", "Concluído"


OPEN_STATUSES = [ProcessStatus.EM_TRAMITACAO, ProcessStatus.SOBRESTADO]


class Priority(models.TextChoices):
    """Prioridade legal de tramitação (Lei 9.784/1999, art. 69-A)."""

    NORMAL = "NORMAL", "Normal"
    IDOSO = "IDOSO", "Pessoa idosa (60 anos ou mais)"
    DEFICIENCIA = "DEFICIENCIA", "Pessoa com deficiência"
    DOENCA_GRAVE = "DOENCA_GRAVE", "Doença grave"
    JUDICIAL = "JUDICIAL", "Determinação judicial"


class Process(InstitutionScopedModel):
    number = models.PositiveIntegerField("número")
    year = models.PositiveSmallIntegerField("ano")
    process_type = models.ForeignKey(ProcessType, on_delete=models.PROTECT, related_name="+", verbose_name="tipo")
    subject = models.CharField("assunto", max_length=255)
    description = models.TextField("descrição", blank=True)
    interested = models.ForeignKey("people.Person", on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="processes", verbose_name="interessado (Cadastro Único)")
    interested_name = models.CharField("interessado", max_length=150)
    interested_cpf = models.CharField("CPF/CNPJ do interessado", max_length=14, blank=True)
    priority = models.CharField("prioridade", max_length=15, choices=Priority.choices, default=Priority.NORMAL)
    external_number = models.CharField("número de origem / externo", max_length=40, blank=True)
    status = models.CharField("situação", max_length=15, choices=ProcessStatus.choices,
                              default=ProcessStatus.EM_TRAMITACAO)
    current_sector = models.ForeignKey(Sector, on_delete=models.PROTECT, related_name="+",
                                       verbose_name="setor atual")
    pending_receipt = models.BooleanField("aguardando recebimento", default=False)
    opened_at = models.DateTimeField("aberto em")
    opened_date = models.DateField("data de abertura")
    business_days = models.BooleanField("prazo em dias úteis", default=True)
    deadline_days = models.PositiveSmallIntegerField("prazo (dias)")
    due_date = models.DateField("vencimento")
    sector_due_date = models.DateField("vencimento no setor", null=True, blank=True)
    suspended_since = models.DateField("sobrestado desde", null=True, blank=True)
    closed_at = models.DateTimeField("encerrado em", null=True, blank=True)

    class Meta:
        db_table = "protocol_processes"
        verbose_name = "processo"
        ordering = ["-year", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "year", "number"], name="uq_process_number"),
            models.CheckConstraint(condition=~Q(status="SOBRESTADO") | Q(suspended_since__isnull=False),
                                   name="ck_process_suspended_since"),
        ]
        indexes = [models.Index(fields=["institution", "status", "due_date"])]

    def __str__(self):
        return self.code

    @property
    def code(self) -> str:
        return f"{self.number:06d}/{self.year}"


class ProtocolCounter(models.Model):
    """Sequência anual de numeração por instituição (travada com SELECT ... FOR UPDATE)."""

    institution = models.ForeignKey("institutions.Institution", on_delete=models.PROTECT, related_name="+")
    year = models.PositiveSmallIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "protocol_counters"
        constraints = [models.UniqueConstraint(fields=["institution", "year"], name="uq_protocol_counter")]


class MovementKind(models.TextChoices):
    ABERTURA = "ABERTURA", "Abertura"
    ENVIO = "ENVIO", "Envio a outro setor"
    RECEBIMENTO = "RECEBIMENTO", "Recebimento"
    DESPACHO = "DESPACHO", "Despacho"
    SOBRESTAMENTO = "SOBRESTAMENTO", "Sobrestamento"
    RETOMADA = "RETOMADA", "Retomada"
    PRORROGACAO = "PRORROGACAO", "Prorrogação de prazo"
    CONCLUSAO = "CONCLUSAO", "Conclusão"
    ARQUIVAMENTO = "ARQUIVAMENTO", "Arquivamento"
    DESARQUIVAMENTO = "DESARQUIVAMENTO", "Desarquivamento"


class Movement(InstitutionScopedModel):
    """Andamento do processo. Registro imutável."""

    process = models.ForeignKey(Process, on_delete=models.PROTECT, related_name="movements", verbose_name="processo")
    kind = models.CharField("tipo", max_length=16, choices=MovementKind.choices)
    from_sector = models.ForeignKey(Sector, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                    verbose_name="setor de origem")
    to_sector = models.ForeignKey(Sector, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                  verbose_name="setor de destino")
    text = models.TextField("despacho / justificativa", blank=True)
    occurred_at = models.DateTimeField("data/hora")
    due_date_after = models.DateField("vencimento após o andamento", null=True, blank=True)

    class Meta:
        db_table = "protocol_movements"
        verbose_name = "andamento"
        ordering = ["occurred_at", "created_at"]


class Attachment(InstitutionScopedModel):
    process = models.ForeignKey(Process, on_delete=models.PROTECT, related_name="attachments", verbose_name="processo")
    description = models.CharField("descrição", max_length=255)
    file = models.FileField("arquivo", upload_to="protocolo/%Y/%m/")
    file_name = models.CharField("nome original", max_length=255)
    file_size = models.PositiveIntegerField("tamanho")
    content_type = models.CharField("tipo", max_length=100)
    sha256 = models.CharField("hash SHA-256", max_length=64)

    class Meta:
        db_table = "protocol_attachments"
        verbose_name = "anexo"
        ordering = ["created_at"]
