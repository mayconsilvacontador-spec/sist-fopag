from django.apps import AppConfig


class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.alerts"
    verbose_name = "Central de Alertas"

    def ready(self):
        from apps.audit.registry import register

        from . import checks  # noqa: F401  (registra as verificações)
        from .models import Alert

        register(Alert, module="alertas")
