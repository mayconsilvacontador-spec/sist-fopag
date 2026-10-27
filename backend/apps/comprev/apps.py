from django.apps import AppConfig


class ComprevConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.comprev"
    verbose_name = "COMPREV"

    def ready(self):
        from . import alert_checks, reports  # noqa: F401  (alertas e relatórios)
