"""
Permissão DRF baseada em módulo + ação.

Uso em uma view/viewset:

    class UserViewSet(ModelViewSet):
        module_code = "admin.usuarios"
        # opcional: ações customizadas
        action_permissions = {"reset_password": "editar"}

Mapeamento padrão:
    list/retrieve/GET  -> visualizar
    create/POST        -> incluir
    update/PUT/PATCH   -> editar
    destroy/DELETE     -> excluir

Views sem module_code exigem apenas autenticação.
Esta classe também resolve a instituição corrente (request.institution) e
atualiza o contexto de auditoria com o usuário autenticado via JWT.
"""
from rest_framework.permissions import BasePermission

from apps.core.context import update_context

DEFAULT_ACTION_MAP = {
    "list": "visualizar",
    "retrieve": "visualizar",
    "create": "incluir",
    "update": "editar",
    "partial_update": "editar",
    "destroy": "excluir",
}
METHOD_MAP = {
    "GET": "visualizar",
    "HEAD": "visualizar",
    "OPTIONS": "visualizar",
    "POST": "incluir",
    "PUT": "editar",
    "PATCH": "editar",
    "DELETE": "excluir",
}


def attach_request_context(request) -> None:
    """Resolve instituição e permissões uma única vez por requisição."""
    if getattr(request, "_sist_ctx_ready", False):
        return
    from . import services  # import tardio: evita import circular com rest_framework.views
    user = request.user
    institution = services.resolve_institution(user, request.headers.get("X-Institution-Id"))
    request.institution = institution
    request.permission_keys = services.get_permission_keys(user, institution)
    update_context(user=user, institution_id=str(institution.pk) if institution else None)
    request._sist_ctx_ready = True


class ModulePermission(BasePermission):
    message = "Você não possui permissão para executar esta ação."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            # IsAuthenticated (ou AllowAny) decide; aqui não bloqueamos
            return getattr(view, "allow_anonymous", False)

        # Usuário do Portal do Segurado só acessa rotas marcadas como do portal (dados do próprio segurado)
        if getattr(user, "is_portal", False) and not getattr(view, "portal_allowed", False):
            self.message = "Acesso restrito ao Portal do Segurado."
            return False

        attach_request_context(request)

        if user.must_change_password and not getattr(view, "allow_pending_password", False):
            self.message = {
                "detail": "É necessário trocar a senha antes de continuar.",
                "code": "troca_senha_obrigatoria",
            }
            return False

        module_code = getattr(view, "module_code", None)
        if not module_code:
            return True

        if request.institution is None:
            self.message = "Usuário sem acesso ativo a nenhuma instituição."
            return False

        action = self._resolve_action(request, view)
        return f"{module_code}:{action}" in request.permission_keys

    @staticmethod
    def _resolve_action(request, view) -> str:
        view_action = getattr(view, "action", None)
        custom = getattr(view, "action_permissions", {}) or {}
        if view_action and view_action in custom:
            return custom[view_action]
        if request.method in custom:
            return custom[request.method]
        if view_action and view_action in DEFAULT_ACTION_MAP:
            return DEFAULT_ACTION_MAP[view_action]
        return METHOD_MAP.get(request.method, "visualizar")


def has_perm(request, key: str) -> bool:
    attach_request_context(request)
    return key in request.permission_keys
