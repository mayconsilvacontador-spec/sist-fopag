from django.apps import AppConfig


class ProvaDeVidaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.provadevida"
    verbose_name = "Prova de Vida"

    def ready(self):
        from . import alert_checks, reports  # noqa: F401  (alertas e relatórios)
