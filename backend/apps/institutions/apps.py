from django.apps import AppConfig


class InstitutionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.institutions"
    verbose_name = "Instituições"

    def ready(self):
        from apps.audit.registry import register

        from . import models

        register(models.Institution, module="admin.instituicao")
        register(models.BenefitPlan, module="admin.instituicao")
        register(models.PayrollGroup, module="admin.instituicao")
        register(models.LifePurchase, module="admin.instituicao")
        register(models.FiscalYear, module="admin.exercicios")
        register(models.Competence, module="admin.competencias")
        register(models.Parameter, module="admin.parametros")
