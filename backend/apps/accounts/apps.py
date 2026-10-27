from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_after_migrate(sender, **kwargs):
    from .services import sync_permissions

    sync_permissions(verbose=False)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Usuários e Permissões"

    def ready(self):
        from apps.audit.registry import register

        from . import models

        register(
            models.User, module="admin.usuarios",
            exclude=["last_login", "failed_login_attempts", "last_login_ip"],
            redact=["password"],
        )
        register(models.Role, module="admin.perfis")
        register(models.Membership, module="admin.usuarios")
        # Concessões de perfis e permissões são auditadas pelos serviços
        # com ação PERMISSION_CHANGE (lista anterior x nova), mais legível.
        post_migrate.connect(_sync_after_migrate, sender=self, dispatch_uid="sist_sync_permissions")
