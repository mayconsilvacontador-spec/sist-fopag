"""
Log de auditoria IMUTÁVEL.

- A aplicação nunca altera nem exclui registros (save/delete bloqueados).
- No PostgreSQL, um trigger (migration 0002) bloqueia UPDATE, DELETE e
  TRUNCATE em audit_logs, inclusive para o usuário da aplicação.
- Cada registro possui hash SHA-256 do seu conteúdo para evidenciar
  adulteração (verificável pelo endpoint /audit/logs/{id}/verify/).
"""
import hashlib
import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class AuditAction(models.TextChoices):
    CREATE = "CREATE", "Inclusão"
    UPDATE = "UPDATE", "Alteração"
    DELETE = "DELETE", "Exclusão"
    LOGIN = "LOGIN", "Login"
    LOGIN_FAILED = "LOGIN_FAILED", "Falha de login"
    LOGOUT = "LOGOUT", "Logout"
    PASSWORD_CHANGE = "PASSWORD_CHANGE", "Troca de senha"
    PERMISSION_CHANGE = "PERMISSION_CHANGE", "Alteração de permissão"
    CALCULATE = "CALCULATE", "Cálculo"
    CLOSE = "CLOSE", "Fechamento"
    REOPEN = "REOPEN", "Reabertura"
    CANCEL = "CANCEL", "Cancelamento"
    EXPORT = "EXPORT", "Exportação"
    APPROVE = "APPROVE", "Aprovação"
    SYSTEM = "SYSTEM", "Sistema"


class ImmutableAuditError(Exception):
    pass


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    timestamp = models.DateTimeField("data/hora", db_index=True)
    institution = models.ForeignKey(
        "institutions.Institution", null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="instituição",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="usuário",
    )
    username = models.CharField("usuário (registro)", max_length=150, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    user_agent = models.CharField("navegador", max_length=400, blank=True)
    request_id = models.CharField("requisição", max_length=64, blank=True, db_index=True)
    source = models.CharField("origem", max_length=20, default="web")
    action = models.CharField("ação", max_length=20, choices=AuditAction.choices, db_index=True)
    module = models.CharField("módulo", max_length=80, blank=True, db_index=True)
    object_type = models.CharField("tipo de registro", max_length=100, blank=True, db_index=True)
    object_id = models.CharField("ID do registro", max_length=64, blank=True, db_index=True)
    object_repr = models.CharField("registro", max_length=255, blank=True)
    old_values = models.JSONField("valores anteriores", null=True, blank=True, encoder=DjangoJSONEncoder)
    new_values = models.JSONField("valores novos", null=True, blank=True, encoder=DjangoJSONEncoder)
    justification = models.TextField("justificativa", blank=True)
    extra = models.JSONField("dados adicionais", null=True, blank=True, encoder=DjangoJSONEncoder)
    record_hash = models.CharField("hash SHA-256", max_length=64)

    class Meta:
        db_table = "audit_logs"
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["institution", "-timestamp"]),
            models.Index(fields=["object_type", "object_id"]),
        ]
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.timestamp:%d/%m/%Y %H:%M:%S} {self.action} {self.object_repr}"

    # -- imutabilidade ----------------------------------------------------
    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableAuditError("Registros de auditoria não podem ser alterados.")
        self.record_hash = self.compute_hash()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableAuditError("Registros de auditoria não podem ser excluídos.")

    # -- integridade ------------------------------------------------------
    def hash_payload(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "institution": str(self.institution_id) if self.institution_id else None,
            "user": str(self.user_id) if self.user_id else None,
            "username": self.username,
            "ip": self.ip,
            "action": self.action,
            "module": self.module,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "old_values": self.old_values,
            "new_values": self.new_values,
            "justification": self.justification,
        }

    def compute_hash(self) -> str:
        raw = json.dumps(self.hash_payload(), cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def verify(self) -> bool:
        # Recarrega do banco para comparar o conteúdo efetivamente gravado
        stored = AuditLog.objects.get(pk=self.pk)
        return stored.compute_hash() == stored.record_hash
