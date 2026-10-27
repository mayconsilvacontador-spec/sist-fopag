"""
Usuários, perfis e permissões (RBAC por módulo + ação), com acesso por
instituição (membership).
"""
import uuid

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import BaseModel
from apps.core.validators import validate_cpf

from .catalog import ACTIONS


class SistUserManager(UserManager):
    pass


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Substitui first_name/last_name por nome completo (padrão brasileiro)
    first_name = None
    last_name = None
    full_name = models.CharField("nome completo", max_length=200)
    cpf = models.CharField(
        "CPF", max_length=11, null=True, blank=True, unique=True, validators=[validate_cpf],
        help_text="Somente dígitos.",
    )
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefone", max_length=20, blank=True)
    job_title = models.CharField("cargo/função", max_length=120, blank=True)
    default_institution = models.ForeignKey(
        "institutions.Institution", null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="instituição padrão",
    )
    failed_login_attempts = models.PositiveSmallIntegerField("tentativas de login falhas", default=0)
    locked_until = models.DateTimeField("bloqueado até", null=True, blank=True)
    must_change_password = models.BooleanField("deve trocar a senha", default=True)
    password_changed_at = models.DateTimeField("senha alterada em", null=True, blank=True)
    last_login_ip = models.GenericIPAddressField("IP do último login", null=True, blank=True)
    is_portal = models.BooleanField(
        "usuário do Portal do Segurado", default=False,
        help_text="Segurado/beneficiário: acessa somente o Portal (próprios dados), nunca as telas internas.",
    )

    REQUIRED_FIELDS = ["full_name", "email"]

    objects = SistUserManager()

    class Meta:
        db_table = "users"
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.username})"

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return (self.full_name or self.username).split(" ")[0]

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())


class Module(models.Model):
    """Módulo/tela do sistema (sincronizado a partir de catalog.py)."""

    code = models.CharField("código", max_length=80, primary_key=True)
    name = models.CharField("nome", max_length=120)
    group = models.CharField("grupo", max_length=40)
    order = models.PositiveIntegerField("ordem", default=0)
    phase = models.PositiveSmallIntegerField("fase", null=True, blank=True)
    implemented = models.BooleanField("implementado", default=False)

    class Meta:
        db_table = "modules"
        verbose_name = "módulo"
        verbose_name_plural = "módulos"
        ordering = ["order"]

    def __str__(self):
        return self.name


class AccessPermission(models.Model):
    """Permissão = módulo + ação."""

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="permissions")
    action = models.CharField("ação", max_length=20, choices=ACTIONS)

    class Meta:
        db_table = "permissions"
        verbose_name = "permissão"
        verbose_name_plural = "permissões"
        ordering = ["module__order", "action"]
        constraints = [
            models.UniqueConstraint(fields=["module", "action"], name="uq_permission_module_action"),
        ]

    def __str__(self):
        return f"{self.module_id}:{self.action}"

    @property
    def key(self) -> str:
        return f"{self.module_id}:{self.action}"


class Role(BaseModel):
    """
    Perfil de acesso. institution nulo = perfil de sistema (compartilhado por
    todas as instituições). Perfis de sistema não podem ser excluídos.
    """

    institution = models.ForeignKey(
        "institutions.Institution", null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="instituição",
    )
    code = models.CharField("código", max_length=40)
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    is_system = models.BooleanField("perfil de sistema", default=False)
    active = models.BooleanField("ativo", default=True)
    permissions = models.ManyToManyField(
        AccessPermission, through="RolePermission", related_name="roles", blank=True,
    )

    class Meta:
        db_table = "roles"
        verbose_name = "perfil"
        verbose_name_plural = "perfis"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"], condition=Q(institution__isnull=True), name="uq_role_system_code",
            ),
            models.UniqueConstraint(
                fields=["institution", "code"], condition=Q(institution__isnull=False),
                name="uq_role_institution_code",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_master(self) -> bool:
        return self.code == "MASTER" and self.is_system


class RolePermission(models.Model):
    """Tabela explícita para que cada concessão/revogação seja auditada."""

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(AccessPermission, on_delete=models.CASCADE, related_name="+")
    granted_at = models.DateTimeField("concedida em", default=timezone.now)

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uq_role_permission"),
        ]


class Membership(BaseModel):
    """Acesso de um usuário a uma instituição, com um ou mais perfis."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    institution = models.ForeignKey(
        "institutions.Institution", on_delete=models.PROTECT, related_name="memberships",
    )
    roles = models.ManyToManyField(Role, through="MembershipRole", related_name="memberships")
    active = models.BooleanField("ativo", default=True)
    valid_from = models.DateField("início do acesso", default=timezone.localdate)
    valid_to = models.DateField("fim do acesso", null=True, blank=True)

    class Meta:
        db_table = "memberships"
        verbose_name = "acesso à instituição"
        verbose_name_plural = "acessos às instituições"
        constraints = [
            models.UniqueConstraint(fields=["user", "institution"], name="uq_membership"),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.institution}"

    def is_current(self) -> bool:
        today = timezone.localdate()
        return self.active and self.valid_from <= today and (self.valid_to is None or self.valid_to >= today)


class MembershipRole(models.Model):
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="membership_roles")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="+")
    granted_at = models.DateTimeField("concedido em", default=timezone.now)

    class Meta:
        db_table = "membership_roles"
        constraints = [
            models.UniqueConstraint(fields=["membership", "role"], name="uq_membership_role"),
        ]
