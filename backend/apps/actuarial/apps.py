from django.apps import AppConfig


class ActuarialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.actuarial"
    verbose_name = "Avaliação Atuarial"

    def ready(self):
        from apps.audit.registry import register

        from . import models, sources  # noqa: F401  (sources registra as origens de dados)

        register(models.ActuarialBase, module="atuarial.base")
