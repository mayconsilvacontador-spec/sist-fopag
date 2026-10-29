from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.people"
    verbose_name = "Cadastro de pessoas"

    def ready(self):
        from apps.audit.registry import register

        from . import models

        register(models.Person, module="cadastros.segurados")
        register(models.Address, module="cadastros.segurados")
        register(models.BankAccount, module="cadastros.segurados")
        register(models.Dependency, module="cadastros.dependentes")
        register(models.Document, module="cadastros.segurados", exclude=["file"])
