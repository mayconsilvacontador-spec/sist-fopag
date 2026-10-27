from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.core.context import get_context, update_context
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import format_cpf
from apps.institutions.models import Institution
from apps.people.receita import is_configured as receita_configured

from . import services
from .catalog import ACTIONS, GROUPS
from .models import Membership, Module, Role, User
from .permissions import attach_request_context
from .serializers import (
    ChangePasswordSerializer, LoginSerializer, ModuleSerializer, RoleSerializer, UserSerializer,
    generate_temporary_password,
)

GENERIC_LOGIN_ERROR = "Usuário ou senha inválidos."
_DUMMY_HASH = make_password("sist-dummy-password-for-timing")


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
class LoginView(APIView):
    """
    Autentica e devolve tokens JWT. Falhas retornam resposta (sem exceção)
    para que o contador de tentativas e a auditoria sejam gravados.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        username = ser.validated_data["username"].strip().lower()
        password = ser.validated_data["password"]

        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            # Equaliza o tempo de resposta para não revelar logins existentes
            from django.contrib.auth.hashers import check_password
            check_password(password, _DUMMY_HASH)
            services.register_login_failure(None, username, "usuario_inexistente")
            return self._fail(GENERIC_LOGIN_ERROR)

        if user.is_locked:
            services.register_login_failure(user, username, "usuario_bloqueado")
            minutes = max(1, int((user.locked_until - timezone.now()).total_seconds() // 60) + 1)
            return self._fail(
                f"Acesso temporariamente bloqueado por excesso de tentativas. Tente novamente em {minutes} minuto(s).",
                code="usuario_bloqueado",
            )

        if not user.check_password(password):
            services.register_login_failure(user, username, "senha_incorreta")
            return self._fail(GENERIC_LOGIN_ERROR)

        if not user.is_active:
            services.register_login_failure(user, username, "usuario_inativo")
            return self._fail(GENERIC_LOGIN_ERROR)

        if user.is_portal:  # segurado entra pelo Portal (portal/auth/token/)
            services.register_login_failure(user, username, "usuario_portal")
            return self._fail(GENERIC_LOGIN_ERROR)

        institution = services.resolve_institution(user, None)
        if institution is None:
            services.register_login_failure(user, username, "sem_instituicao")
            return self._fail("Usuário sem acesso ativo a nenhuma instituição. Procure o administrador.",
                              code="sem_instituicao")

        update_context(user=user, institution_id=str(institution.pk))
        services.register_login_success(user, get_context().ip)
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "must_change_password": user.must_change_password,
            "institution_id": str(institution.pk),
        })

    @staticmethod
    def _fail(message, code="credenciais_invalidas"):
        return Response({"detail": message, "code": code}, status=status.HTTP_401_UNAUTHORIZED)


class SistTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            token = RefreshToken(attrs["refresh"])
        except TokenError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        user = User.objects.filter(pk=token.payload.get(jwt_settings.USER_ID_CLAIM)).first()
        if user is None or not user.is_active or user.is_locked:
            raise serializers.ValidationError({"detail": "Sessão inválida."})
        return super().validate(attrs)


class RefreshView(TokenRefreshView):
    serializer_class = SistTokenRefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw = request.data.get("refresh")
        if not raw:
            return Response(status=status.HTTP_204_NO_CONTENT)
        try:
            token = RefreshToken(raw)
            user = User.objects.filter(pk=token.payload.get(jwt_settings.USER_ID_CLAIM)).first()
            token.blacklist()
            if user:
                log_event(AuditAction.LOGOUT, module="acesso", obj=user, user=user,
                          institution_id=user.default_institution_id)
        except TokenError:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Dados do usuário logado, instituição corrente, perfis e permissões."""

    permission_classes = [IsAuthenticated]
    allow_pending_password = True
    portal_allowed = True

    def get(self, request):
        user = request.user
        if user.is_portal:
            return Response({"portal": True, "user": {"id": str(user.pk), "full_name": user.full_name,
                                                      "must_change_password": user.must_change_password}})
        attach_request_context(request)
        inst = request.institution
        memberships = services.active_memberships(user)
        institutions = [m.institution for m in memberships]
        if user.is_superuser:
            institutions = list(Institution.objects.filter(active=True))
        roles = services.get_user_roles(user, inst)
        modules = Module.objects.prefetch_related("permissions").all()
        return Response({
            "user": {
                "id": str(user.pk),
                "username": user.username,
                "full_name": user.full_name,
                "short_name": user.get_short_name(),
                "email": user.email,
                "cpf": format_cpf(user.cpf) if user.cpf else "",
                "must_change_password": user.must_change_password,
                "last_login": user.last_login,
                "is_master": services.user_is_master(user, inst),
            },
            "institution": _institution_payload(inst) if inst else None,
            "institutions": [_institution_payload(i) for i in institutions],
            "roles": [{"id": str(r.pk), "code": r.code, "name": r.name} for r in roles],
            "primary_role": _primary_role(roles),
            "permissions": sorted(request.permission_keys),
            "modules": ModuleSerializer(modules, many=True).data,
            "groups": [{"code": c, "name": n} for c, n in GROUPS],
            "actions": [{"code": c, "name": n} for c, n in ACTIONS],
            "integracoes": {"receita": receita_configured()},
        })


def _institution_payload(inst: Institution) -> dict:
    return {
        "id": str(inst.pk), "short_name": inst.short_name, "name": inst.name,
        "city": inst.city, "uf": inst.uf, "kind": inst.kind, "life_purchase_enabled": inst.life_purchase_enabled,
    }


ROLE_PRIORITY = ["MASTER", "ADMINISTRADOR", "AUDITOR", "PREVIDENCIARIO", "FOLHA", "FINANCEIRO",
                 "CONTABILIDADE", "CONSULTA"]


def _primary_role(roles) -> str:
    codes = [r.code for r in roles]
    for code in ROLE_PRIORITY:
        if code in codes:
            return code
    return codes[0] if codes else "SEM PERFIL"


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    allow_pending_password = True
    portal_allowed = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=ChangePasswordSerializer, responses={200: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request):
        attach_request_context(request)
        ser = ChangePasswordSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        user = request.user
        user.set_password(ser.validated_data["new_password"])
        user.must_change_password = False
        user.password_changed_at = timezone.now()
        user.save()
        # Encerra todas as sessões abertas do usuário
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        log_event(AuditAction.PASSWORD_CHANGE, module="acesso", obj=user)
        return Response({"detail": "Senha alterada com sucesso. Entre novamente."})


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------
class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Usuários com acesso à instituição corrente. Usuários não são excluídos: são inativados."""

    module_code = "admin.usuarios"
    serializer_class = UserSerializer
    search_fields = ["username", "full_name", "email", "cpf"]
    ordering_fields = ["full_name", "username", "last_login", "date_joined"]
    action_permissions = {
        "activate": "editar", "deactivate": "editar", "unlock": "editar", "reset_password": "editar",
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        qs = User.objects.filter(memberships__institution=self.request.institution).distinct()
        status_f = self.request.query_params.get("status")
        if status_f == "ativos":
            qs = qs.filter(is_active=True)
        elif status_f == "inativos":
            qs = qs.filter(is_active=False)
        elif status_f == "bloqueados":
            qs = qs.filter(locked_until__gt=timezone.now())
        role = self.request.query_params.get("perfil")
        if role:
            qs = qs.filter(memberships__institution=self.request.institution,
                           memberships__roles__code=role)
        return qs.order_by("full_name")

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if user.pk == request.user.pk:
            raise BusinessRuleError("Você não pode inativar o próprio usuário.")
        if services.user_is_master(user, request.institution) and not services.user_is_master(request.user, request.institution):
            raise BusinessRuleError("Somente usuários MASTER podem inativar outro MASTER.")
        user.is_active = False
        user.save()
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        user = self.get_object()
        user.locked_until = None
        user.failed_login_attempts = 0
        user.save()
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        if services.user_is_master(user, request.institution) and not services.user_is_master(request.user, request.institution):
            raise BusinessRuleError("Somente usuários MASTER podem redefinir a senha de outro MASTER.")
        temp = generate_temporary_password()
        user.set_password(temp)
        user.must_change_password = True
        user.locked_until = None
        user.failed_login_attempts = 0
        user.save()
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        log_event(AuditAction.PASSWORD_CHANGE, module="admin.usuarios", obj=user,
                  extra={"tipo": "redefinicao_administrativa"})
        return Response({"temporary_password": temp,
                         "detail": "Senha temporária gerada. Ela será exibida apenas uma vez."})


# ---------------------------------------------------------------------------
# Perfis e permissões
# ---------------------------------------------------------------------------
class RoleViewSet(viewsets.ModelViewSet):
    module_code = "admin.perfis"
    serializer_class = RoleSerializer
    search_fields = ["code", "name"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Role.objects.none()
        return Role.objects.filter(
            Q(institution__isnull=True) | Q(institution=self.request.institution)
        ).order_by("-is_system", "name")

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution, is_system=False)

    def perform_update(self, serializer):
        role = serializer.instance
        if role.is_system and not services.user_is_master(self.request.user, self.request.institution):
            raise BusinessRuleError("Somente usuários MASTER podem alterar perfis de sistema.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_system:
            raise BusinessRuleError("Perfis de sistema não podem ser excluídos. Inative-os se necessário.")
        if instance.memberships.exists():
            raise BusinessRuleError("O perfil está atribuído a usuários. Retire-o dos usuários antes de excluir.")
        instance.delete()


class RolePermissionsView(APIView):
    """GET: permissões do perfil. PUT: substitui as permissões (auditado)."""

    module_code = "admin.permissoes"

    def _get_role(self, request, pk):
        role = Role.objects.filter(
            Q(institution__isnull=True) | Q(institution=request.institution), pk=pk
        ).first()
        if role is None:
            raise ValidationError({"detail": "Perfil não encontrado."})
        return role

    def get(self, request, pk):
        role = self._get_role(request, pk)
        keys = sorted(f"{m}:{a}" for m, a in role.permissions.values_list("module_id", "action"))
        return Response({"role": RoleSerializer(role, context={"request": request}).data, "permissions": keys})

    def put(self, request, pk):
        role = self._get_role(request, pk)
        keys = request.data.get("permissions")
        if not isinstance(keys, list):
            raise ValidationError({"permissions": "Informe a lista de permissões."})
        services.set_role_permissions(role, keys, request.user, request.institution)
        return self.get(request, pk)


class PermissionMatrixView(APIView):
    """Matriz módulos x ações x perfis."""

    module_code = "admin.permissoes"

    def get(self, request):
        roles = Role.objects.filter(
            Q(institution__isnull=True) | Q(institution=request.institution), active=True
        ).order_by("-is_system", "name")
        modules = Module.objects.prefetch_related("permissions").all()
        return Response({
            "groups": [{"code": c, "name": n} for c, n in GROUPS],
            "actions": [{"code": c, "name": n} for c, n in ACTIONS],
            "modules": ModuleSerializer(modules, many=True).data,
            "roles": [
                {
                    "id": str(r.pk), "code": r.code, "name": r.name, "is_system": r.is_system,
                    "is_master": r.is_master,
                    "permissions": sorted(f"{m}:{a}" for m, a in r.permissions.values_list("module_id", "action")),
                }
                for r in roles
            ],
        })


class MembershipSummaryView(APIView):
    """Resumo de acessos por perfil na instituição corrente (para o painel de administração)."""

    module_code = "admin.usuarios"

    def get(self, request):
        qs = Membership.objects.filter(institution=request.institution, active=True, user__is_active=True)
        return Response({
            "usuarios_ativos": qs.count(),
            "usuarios_bloqueados": User.objects.filter(
                memberships__institution=request.institution, locked_until__gt=timezone.now()
            ).distinct().count(),
            "sem_perfil": qs.filter(membership_roles__isnull=True).count(),
        })
