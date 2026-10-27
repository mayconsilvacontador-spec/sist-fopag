"""
Central de alertas.

Alertas são gerados por verificações automáticas (apps.alerts.checks), de
forma idempotente: cada ocorrência tem uma "impressão digital" (fingerprint)
e, quando a inconsistência deixa de existir, o alerta é resolvido
automaticamente.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel


class Severity(models.TextChoices):
    CRITICO = "CRITICO", "Crítico"
    ATENCAO = "ATENCAO", "Atenção"
    INFORMATIVO = "INFORMATIVO", "Informativo"


class AlertStatus(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    RESOLVIDO = "RESOLVIDO", "Resolvido"
    DESCARTADO = "DESCARTADO", "Descartado"


SEVERITY_ORDER = {Severity.CRITICO: 0, Severity.ATENCAO: 1, Severity.INFORMATIVO: 2}


class Alert(InstitutionScopedModel):
    severity = models.CharField("classificação", max_length=12, choices=Severity.choices)
    code = models.CharField("código da verificação", max_length=60, db_index=True)
    module = models.CharField("módulo", max_length=80)
    title = models.CharField("título", max_length=200)
    message = models.TextField("mensagem", blank=True)
    link = models.CharField("link no sistema", max_length=255, blank=True)
    object_type = models.CharField("tipo do registro", max_length=100, blank=True)
    object_id = models.CharField("ID do registro", max_length=64, blank=True)
    fingerprint = models.CharField("impressão digital", max_length=200)
    is_demo = models.BooleanField("dado de demonstração (DEMO)", default=False)
    status = models.CharField("situação", max_length=12, choices=AlertStatus.choices, default=AlertStatus.ABERTO)
    detected_at = models.DateTimeField("detectado em", auto_now_add=True)
    last_seen_at = models.DateTimeField("última verificação", auto_now_add=True)
    resolved_at = models.DateTimeField("resolvido em", null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="resolvido por",
    )
    resolution_note = models.TextField("observação da resolução", blank=True)

    class Meta:
        db_table = "alerts"
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        ordering = ["status", "-detected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "fingerprint"], condition=Q(status="ABERTO"),
                name="uq_alert_open_fingerprint",
            ),
        ]
        indexes = [models.Index(fields=["institution", "status", "severity"])]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"
