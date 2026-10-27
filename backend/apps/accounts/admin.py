from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Membership, Module, Role, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["full_name"]
    list_display = ["username", "full_name", "email", "is_active", "is_superuser", "last_login"]
    search_fields = ["username", "full_name", "email", "cpf"]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Dados pessoais", {"fields": ("full_name", "cpf", "email", "phone", "job_title", "default_institution")}),
        ("Segurança", {"fields": ("is_active", "is_staff", "is_superuser", "must_change_password",
                                  "failed_login_attempts", "locked_until")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "full_name", "email", "password1", "password2")}),
    )
    filter_horizontal = ()
    list_filter = ["is_active", "is_superuser"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_system", "active"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "institution", "active", "valid_from", "valid_to"]


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "group", "phase", "implemented"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
