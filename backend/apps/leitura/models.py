"""
Leitura inteligente de processos: os PDFs do processo (normalmente digitalizados) são lidos por IA com visão, que
reconhece cada documento (CTC, histórico funcional, contracheque, RG/CPF...) e extrai os dados com a página de
origem. A equipe CONFERE (confirma ou corrige) e só então os dados vão para o Cadastro Único. Nada é concedido
sozinho e nada já cadastrado é sobrescrito sem conferência.
"""
from django.db import models

from apps.core.models import InstitutionScopedModel

ENGINES = [("LOCAL", "Leitura local gratuita (OCR no próprio servidor)"),
           ("ANTHROPIC", "Inteligência artificial (API da Anthropic, paga por uso)")]
MODELS = [("claude-opus-5-5", "Claude Opus 5.5 (máxima precisão)"),
          ("claude-sonnet-5-5", "Claude Sonnet 5.5 (mais econômico)")]


class AiSettings(InstitutionScopedModel):
    """Configuração da leitura por instituição. A chave de API (motor IA) fica criptografada (SIST_SECRETS_KEY)."""

    engine = models.CharField("motor de leitura", max_length=10, choices=ENGINES, default="LOCAL")
    enabled = models.BooleanField("IA ativa (motor Anthropic)", default=False)
    api_key = models.BinaryField("chave de API (criptografada)", editable=False, default=b"")
    key_hint = models.CharField("final da chave", max_length=8, blank=True)
    model = models.CharField("modelo", max_length=40, choices=MODELS, default="claude-opus-5-5")
    privacy_ack = models.BooleanField("ciência sobre envio de dados pessoais ao provedor", default=False)
    last_test_at = models.DateTimeField("último teste", null=True, blank=True)
    last_test_result = models.CharField("resultado do teste", max_length=300, blank=True)

    class Meta:
        db_table = "ai_settings"
        constraints = [models.UniqueConstraint(fields=["institution"], name="uq_ai_settings_institution")]


class JobStatus(models.TextChoices):
    LENDO = "LENDO", "Lendo documentos"
    CONFERENCIA = "CONFERENCIA", "Aguardando conferência"
    APLICADO = "APLICADO", "Dados aplicados ao cadastro"
    DESCARTADO = "DESCARTADO", "Descartado"


class ReadingJob(InstitutionScopedModel):
    title = models.CharField("descrição", max_length=200)
    engine = models.CharField("motor de leitura", max_length=10, choices=ENGINES, default="LOCAL")
    status = models.CharField("situação", max_length=12, choices=JobStatus.choices, default=JobStatus.LENDO)
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                               verbose_name="pessoa (após aplicar)")
    checks = models.JSONField("conferências automáticas", default=list, blank=True)
    applied_at = models.DateTimeField("aplicado em", null=True, blank=True)
    applied_summary = models.JSONField("o que foi aplicado", default=dict, blank=True)

    class Meta:
        db_table = "reading_jobs"
        ordering = ["-created_at"]


class FileStatus(models.TextChoices):
    PENDENTE = "PENDENTE", "Na fila"
    LIDO = "LIDO", "Lido"
    ERRO = "ERRO", "Erro na leitura"


class ReadingFile(InstitutionScopedModel):
    job = models.ForeignKey(ReadingJob, on_delete=models.PROTECT, related_name="files")
    file = models.FileField("arquivo", upload_to="leitura/%Y/%m/")
    file_name = models.CharField("nome original", max_length=255)
    file_size = models.PositiveIntegerField("tamanho")
    sha256 = models.CharField("hash SHA-256", max_length=64)
    order = models.PositiveIntegerField("ordem", default=0)
    status = models.CharField("situação", max_length=10, choices=FileStatus.choices, default=FileStatus.PENDENTE)
    pages_total = models.PositiveIntegerField("páginas", default=0)
    pages_done = models.PositiveIntegerField("páginas lidas", default=0)
    error = models.TextField("erro", blank=True)
    result = models.JSONField("documentos encontrados", default=dict, blank=True)
    model = models.CharField("modelo usado", max_length=40, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    read_at = models.DateTimeField("lido em", null=True, blank=True)

    class Meta:
        db_table = "reading_files"
        ordering = ["order", "created_at"]
