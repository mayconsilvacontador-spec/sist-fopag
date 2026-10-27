from django.apps import AppConfig


class FolhaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.folha"
    verbose_name = "Folha de benefícios"

    def ready(self):
        from apps.audit.registry import register

        from . import models

        register(models.Rubric, module="folha.rubricas")
        register(models.Consignee, module="folha.consignacoes")
        register(models.Entry, module="folha.diferencas")
        register(models.IrExemption, module="folha.beneficiarios")
