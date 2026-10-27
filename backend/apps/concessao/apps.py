from django.apps import AppConfig


class ConcessaoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.concessao"
    verbose_name = "Concessão de benefícios"

    def ready(self):
        from apps.audit.registry import register

        from . import alert_checks, models  # noqa: F401  (alertas de cotas temporárias)

        register(models.Concession, module="concessao.processos", exclude=["analysis", "calculation"])
        register(models.Parcel, module="concessao.processos")
        register(models.PensionQuota, module="concessao.pensao")
        register(models.Benefit, module="folha.beneficiarios")
        register(models.DocumentTemplate, module="concessao.modelos")
