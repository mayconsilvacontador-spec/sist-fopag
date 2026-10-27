"""
Modelos-base reutilizados por todos os módulos do SIST.

- UUIDModel: chave primária UUID (evita IDs sequenciais previsíveis em URLs).
- TimeStampedModel: datas de criação/atualização e usuários responsáveis.
- InstitutionScopedModel: toda entidade de negócio pertence a um RPPS.
- ValidityModel: vigência inicial/final para históricos que não podem ser
  sobrescritos.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .context import get_current_user


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", editable=False, verbose_name="criado por",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", editable=False, verbose_name="atualizado por",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        user = get_current_user()
        if user is not None and getattr(user, "is_authenticated", False):
            if self._state.adding and not self.created_by_id:
                self.created_by = user
            self.updated_by = user
        super().save(*args, **kwargs)


class BaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class InstitutionScopedModel(BaseModel):
    institution = models.ForeignKey(
        "institutions.Institution", on_delete=models.PROTECT,
        related_name="+", verbose_name="instituição",
    )

    class Meta:
        abstract = True


class ValidityModel(models.Model):
    """Registro com vigência. valid_to nulo = vigente por prazo indeterminado."""

    valid_from = models.DateField("vigência inicial")
    valid_to = models.DateField("vigência final", null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.valid_to and self.valid_from and self.valid_to < self.valid_from:
            raise ValidationError(
                {"valid_to": "A vigência final não pode ser anterior à inicial."}
            )

    def is_valid_on(self, date) -> bool:
        return self.valid_from <= date and (self.valid_to is None or self.valid_to >= date)
