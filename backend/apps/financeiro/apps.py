from django.apps import AppConfig


class FinanceiroConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.financeiro"
    verbose_name = "Gestão financeira e arrecadação"

    def ready(self):
        from apps.audit.registry import register

        from . import models

        register(models.TreasuryAccount, module="financeiro.bancos")
        register(models.Contribution, module="arrecadacao.servidor")
        register(models.Aporte, module="arrecadacao.aportes")
        register(models.InstallmentAgreement, module="arrecadacao.parcelamentos")
        register(models.AccountingMapping, module="financeiro.integracao_contabil")
