from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reports"
    verbose_name = "Relatórios"

    def ready(self):
        from . import definitions, dipr  # noqa: F401  (registra os relatórios)
