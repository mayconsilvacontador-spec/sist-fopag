from django.apps import AppConfig


class EmploymentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.employment"
    verbose_name = "Vínculos funcionais"

    def ready(self):
        from apps.audit.registry import register

        from . import actuarial_sources, models  # noqa: F401  (registra origens da base atuarial)

        register(models.EmploymentLink, module="cadastros.vinculos")
        register(models.FunctionalEvent, module="cadastros.vinculos")
