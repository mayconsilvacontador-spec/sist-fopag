"""Bases de dados geradas para a avaliação atuarial (histórico imutável)."""
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel


class ActuarialBase(InstitutionScopedModel):
    """
    Uma geração da base de dados atuarial para uma data-base. Cada geração é
    guardada com o arquivo ZIP e seu hash SHA-256 — nunca é sobrescrita nem
    excluída, para que o atuário e os órgãos de controle possam conferir
    exatamente o que foi entregue.
    """

    reference_year = models.PositiveSmallIntegerField("ano da data-base")
    reference_month = models.PositiveSmallIntegerField("mês da data-base")
    layout_code = models.CharField("leiaute", max_length=40)
    life_purchase_enabled = models.BooleanField("compra de vidas na geração", default=False)
    file = models.FileField("arquivo", upload_to="atuarial/%Y/")
    file_name = models.CharField("nome do arquivo", max_length=120)
    file_sha256 = models.CharField("hash SHA-256", max_length=64)
    file_size = models.PositiveIntegerField("tamanho (bytes)")
    summary = models.JSONField("resumo por fundo e arquivo", default=dict)
    pendencias = models.JSONField("pendências", default=list)
    notes = models.TextField("observações", blank=True)

    class Meta:
        db_table = "actuarial_bases"
        verbose_name = "base atuarial"
        verbose_name_plural = "bases atuariais"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(reference_month__gte=1) & Q(reference_month__lte=12), name="ck_actuarial_base_month",
            ),
        ]

    def __str__(self):
        return f"Base atuarial {self.reference_month:02d}/{self.reference_year}"
