from django.apps import AppConfig


class RecadastramentoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recadastramento"
    verbose_name = "Recadastramento"

    def ready(self):
        from . import alert_checks, reports  # noqa: F401  (alertas e relatórios)
