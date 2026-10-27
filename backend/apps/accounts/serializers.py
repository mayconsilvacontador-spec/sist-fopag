import secrets
import string

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.core.validators import format_cpf, is_valid_cpf, only_digits

from . import services
from .models import Module, Role, User


def generate_temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "@#$%&*!?"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd) and any(not c.isalnum() for c in pwd)):
            return pwd


class RoleBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "code", "name", "is_system"]


class UserSerializer(serializers.ModelSerializer):
    # Aceita CPF com máscara; validate_cpf normaliza para 11 dígitos
    cpf = serializers.CharField(max_length=14, required=False, allow_blank=True, allow_null=True)
    cpf_formatado = serializers.SerializerMethodField()
    is_locked = serializers.BooleanField(read_only=True)
    roles = serializers.SerializerMethodField()
    role_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False,
        help_text="Perfis do usuário na instituição corrente.",
    )
    temporary_password = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "full_name", "cpf", "cpf_formatado", "email", "phone", "job_title",
            "is_active", "is_locked", "locked_until", "must_change_password", "last_login",
            "last_login_ip", "date_joined", "roles", "role_ids", "temporary_password",
        ]
        read_only_fields = [
            "is_active", "locked_until", "must_change_password", "last_login",
            "last_login_ip", "date_joined",
        ]

    def get_cpf_formatado(self, obj):
        return format_cpf(obj.cpf) if obj.cpf else ""

    def get_roles(self, obj):
        institution = self.context["request"].institution
        return RoleBriefSerializer(services.get_user_roles(obj, institution), many=True).data

    def validate_username(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(username__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Já existe um usuário com este login.")
        return value

    def validate_cpf(self, value):
        if not value:
            return None
        digits = only_digits(value)
        if not is_valid_cpf(digits):
            raise serializers.ValidationError("CPF inválido.")
        qs = User.objects.filter(cpf=digits)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("CPF já cadastrado para outro usuário.")
        return digits

    def validate_full_name(self, value):
        value = " ".join(value.split())
        if len(value) < 3:
            raise serializers.ValidationError("Informe o nome completo.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        role_ids = validated_data.pop("role_ids", [])
        temp = generate_temporary_password()
        user = User(**validated_data, must_change_password=True, default_institution=request.institution)
        user.set_password(temp)
        user.save()
        services.set_user_roles(user, request.institution, role_ids, request.user)
        user.temporary_password = temp
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context["request"]
        role_ids = validated_data.pop("role_ids", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if role_ids is not None:
            services.set_user_roles(instance, request.institution, role_ids, request.user)
        return instance


class RoleSerializer(serializers.ModelSerializer):
    permission_count = serializers.SerializerMethodField()
    user_count = serializers.SerializerMethodField()
    scope = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id", "code", "name", "description", "is_system", "active",
            "permission_count", "user_count", "scope", "created_at", "updated_at",
        ]
        read_only_fields = ["is_system", "created_at", "updated_at"]

    def get_permission_count(self, obj):
        return obj.role_permissions.count()

    def get_user_count(self, obj):
        institution = self.context["request"].institution
        return obj.memberships.filter(institution=institution, active=True, user__is_active=True).count()

    def get_scope(self, obj):
        return "Sistema" if obj.institution_id is None else "Instituição"

    def validate_code(self, value):
        value = value.strip().upper().replace(" ", "_")
        if self.instance and self.instance.is_system and value != self.instance.code:
            raise serializers.ValidationError("O código de um perfil de sistema não pode ser alterado.")
        institution = self.context["request"].institution
        qs = Role.objects.filter(code=value).filter(institution__isnull=True) | Role.objects.filter(
            code=value, institution=institution
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Já existe um perfil com este código.")
        return value

    def validate(self, attrs):
        if self.instance and self.instance.is_master and attrs.get("active") is False:
            raise serializers.ValidationError("O perfil MASTER não pode ser inativado.")
        return attrs


class ModuleSerializer(serializers.ModelSerializer):
    actions = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = ["code", "name", "group", "order", "phase", "implemented", "actions"]

    def get_actions(self, obj):
        return [p.action for p in obj.permissions.all()]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False, min_length=10)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Senha atual incorreta."})
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "A nova senha deve ser diferente da atual."})
        try:
            password_validation.validate_password(attrs["new_password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs
