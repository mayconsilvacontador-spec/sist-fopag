from django.apps import AppConfig


class CadastrosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cadastros"
    verbose_name = "Cadastros básicos"

    def ready(self):
        from apps.audit.registry import register

        from . import models

        register(models.Ente, module="cadastros.entes")
        register(models.Organ, module="cadastros.orgaos")
        register(models.Position, module="cadastros.cargos")
        register(models.Workplace, module="cadastros.lotacao")
        register(models.Bank, module="cadastros.bancos")
        register(models.BankBranch, module="cadastros.agencias")
