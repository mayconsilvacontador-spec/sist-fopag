from django.apps import AppConfig


class ProtocoloConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.protocolo"
    verbose_name = "Protocolo"

    def ready(self):
        from apps.audit.registry import register

        from . import integrations, models  # noqa: F401  (alertas de prazo e pesquisa global)

        register(models.Sector, module="protocolo.configuracao")
        register(models.ProcessType, module="protocolo.configuracao")
        register(models.Holiday, module="protocolo.configuracao")
        register(models.Process, module="protocolo.processos")
        register(models.Attachment, module="protocolo.processos", exclude=["file"])
