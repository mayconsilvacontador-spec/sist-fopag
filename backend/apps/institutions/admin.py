from django.contrib import admin

from .models import BenefitPlan, Competence, FiscalYear, Institution, Parameter


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ["short_name", "name", "city", "uf", "active"]


@admin.register(BenefitPlan)
class BenefitPlanAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "kind", "institution", "active"]


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ["year", "institution", "status"]


@admin.register(Competence)
class CompetenceAdmin(admin.ModelAdmin):
    list_display = ["__str__", "institution", "status", "is_reference"]


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ["key", "version", "valid_from", "valid_to", "institution"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
