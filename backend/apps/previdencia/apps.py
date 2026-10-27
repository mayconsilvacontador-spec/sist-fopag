from django.apps import AppConfig


class PrevidenciaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.previdencia"
    verbose_name = "Gestão previdenciária"

    def ready(self):
        from apps.audit.registry import register

        from . import models

        register(models.Averbacao, module="previdenciaria.averbacoes")
        register(models.ContributionSalary, module="previdenciaria.historico_contributivo")
        register(models.RetirementRule, module="previdenciaria.regras")
        register(models.Ctc, module="previdenciaria.ctc", exclude=["snapshot"])
