"""Regras de negócio de usuários, perfis e permissões."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.core.context import audit_context
from apps.core.exceptions import BusinessRuleError

from .catalog import ALWAYS_SYNC, GROUPS, MODULES, SYSTEM_ROLES
from .models import AccessPermission, Membership, MembershipRole, Module, Role, RolePermission, User

MASTER = "MASTER"


# ---------------------------------------------------------------------------
# Sincronização do catálogo
# ---------------------------------------------------------------------------
@transaction.atomic
def sync_permissions(verbose: bool = True, reset_roles: bool = False) -> dict:
    """
    Cria/atualiza módulos, permissões e perfis de sistema a partir do
    catálogo. Idempotente. Perfis de sistema recebem as permissões padrão
    apenas na criação (ou com reset_roles=True); o MASTER sempre recebe
    todas as permissões.
    """
    group_order = {g: i for i, (g, _) in enumerate(GROUPS)}
    stats = {"modules": 0, "permissions": 0, "roles": 0}

    for idx, mdef in enumerate(MODULES):
        Module.objects.update_or_create(
            code=mdef.code,
            defaults={
                "name": mdef.name,
                "group": mdef.group,
                "order": group_order.get(mdef.group, 99) * 1000 + idx,
                "phase": mdef.phase,
                "implemented": mdef.implemented,
            },
        )
        stats["modules"] += 1
        existing = set(
            AccessPermission.objects.filter(module_id=mdef.code).values_list("action", flat=True)
        )
        new = [AccessPermission(module_id=mdef.code, action=a) for a in mdef.actions if a not in existing]
        AccessPermission.objects.bulk_create(new)
        stats["permissions"] += len(new)
        # Ações removidas do catálogo deixam de existir
        AccessPermission.objects.filter(module_id=mdef.code).exclude(action__in=mdef.actions).delete()

    Module.objects.exclude(code__in=[m.code for m in MODULES]).delete()

    perm_index = {(p.module_id, p.action): p for p in AccessPermission.objects.all()}
    with audit_context(source="system"):
        for code, spec in SYSTEM_ROLES.items():
            role, created = Role.objects.get_or_create(
                institution=None, code=code,
                defaults={"name": spec["name"], "description": spec["description"], "is_system": True},
            )
            if created:
                stats["roles"] += 1
            if created or reset_roles or code == MASTER:
                wanted = {perm_index[k].pk for k in spec["permissions"]() if k in perm_index}
                current = set(role.role_permissions.values_list("permission_id", flat=True))
                RolePermission.objects.bulk_create(
                    [RolePermission(role=role, permission_id=pid) for pid in wanted - current]
                )
                if code != MASTER or reset_roles:
                    role.role_permissions.exclude(permission_id__in=wanted).delete()
            else:
                # Permissões essenciais entram também nos perfis já existentes (só inclusão — não desfaz personalizações)
                wanted = {perm_index[k].pk for k in spec["permissions"]() & ALWAYS_SYNC if k in perm_index}
                current = set(role.role_permissions.values_list("permission_id", flat=True))
                RolePermission.objects.bulk_create(
                    [RolePermission(role=role, permission_id=pid) for pid in wanted - current])
    if verbose:
        print(f"Módulos: {stats['modules']} | novas permissões: {stats['permissions']} | novos perfis: {stats['roles']}")
    return stats


# ---------------------------------------------------------------------------
# Resolução de instituição e permissões
# ---------------------------------------------------------------------------
def active_memberships(user):
    today = timezone.localdate()
    return (
        Membership.objects.filter(user=user, active=True, institution__active=True, valid_from__lte=today)
        .exclude(valid_to__lt=today)
        .select_related("institution")
    )


def resolve_institution(user, requested_id: str | None):
    """
    Retorna a instituição em que o usuário está operando. A instituição
    pedida (cabeçalho X-Institution-Id) só é aceita se o usuário tiver acesso.
    """
    from apps.institutions.models import Institution

    memberships = list(active_memberships(user))
    allowed = {str(m.institution_id): m.institution for m in memberships}
    if user.is_superuser:
        allowed.update({str(i.pk): i for i in Institution.objects.filter(active=True)})

    if requested_id and requested_id in allowed:
        return allowed[requested_id]
    if user.default_institution_id and str(user.default_institution_id) in allowed:
        return allowed[str(user.default_institution_id)]
    if allowed:
        return sorted(allowed.values(), key=lambda i: i.short_name)[0]
    return None


def get_user_roles(user, institution):
    if institution is None:
        return Role.objects.none()
    return Role.objects.filter(
        active=True,
        pk__in=MembershipRole.objects.filter(
            membership__in=active_memberships(user).filter(institution=institution)
        ).values("role_id"),
    )


def get_permission_keys(user, institution) -> set[str]:
    """
    Conjunto de permissões 'modulo:acao' do usuário na instituição. Módulos que
    não se aplicam ao tipo de órgão (ex.: Concessão numa Prefeitura) são retirados.
    """
    from .catalog import module_available

    if not user or not user.is_authenticated or not user.is_active:
        return set()
    if user.is_superuser or get_user_roles(user, institution).filter(code=MASTER, is_system=True).exists():
        keys = {p.key for p in AccessPermission.objects.all()}
    else:
        roles = get_user_roles(user, institution)
        keys = {
            f"{m}:{a}"
            for m, a in AccessPermission.objects.filter(roles__in=roles).values_list("module_id", "action").distinct()
        }
    kind = getattr(institution, "kind", None)
    return {k for k in keys if module_available(k.split(":", 1)[0], kind)}


def user_is_master(user, institution) -> bool:
    return bool(user.is_superuser or get_user_roles(user, institution).filter(code=MASTER, is_system=True).exists())


# ---------------------------------------------------------------------------
# Alterações de perfis e permissões (auditadas)
# ---------------------------------------------------------------------------
@transaction.atomic
def set_role_permissions(role: Role, keys: list[str], actor, institution) -> Role:
    if role.is_master:
        raise BusinessRuleError("As permissões do perfil MASTER não podem ser alteradas.")
    if role.is_system and not user_is_master(actor, institution):
        raise BusinessRuleError("Somente usuários MASTER podem alterar perfis de sistema.")
    perms = {p.key: p for p in AccessPermission.objects.all()}
    invalid = [k for k in keys if k not in perms]
    if invalid:
        raise BusinessRuleError(f"Permissões inexistentes: {', '.join(invalid[:5])}")
    before = sorted(f"{m}:{a}" for m, a in role.permissions.values_list("module_id", "action"))
    wanted = {perms[k].pk for k in keys}
    current = set(role.role_permissions.values_list("permission_id", flat=True))
    RolePermission.objects.bulk_create([RolePermission(role=role, permission_id=p) for p in wanted - current])
    role.role_permissions.filter(permission_id__in=current - wanted).delete()
    after = sorted(set(keys))
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    if added or removed:
        log_event(
            AuditAction.PERMISSION_CHANGE, module="admin.permissoes", obj=role,
            old={"removidas": removed}, new={"adicionadas": added},
            institution_id=institution.pk if institution else None,
        )
    return role


@transaction.atomic
def set_user_roles(user: User, institution, role_ids: list, actor) -> Membership:
    roles = list(Role.objects.filter(pk__in=role_ids, active=True))
    if len(roles) != len(set(map(str, role_ids))):
        raise BusinessRuleError("Um ou mais perfis informados não existem ou estão inativos.")
    for r in roles:
        if r.institution_id and r.institution_id != institution.pk:
            raise BusinessRuleError(f"O perfil {r.name} pertence a outra instituição.")
    membership, _ = Membership.objects.get_or_create(user=user, institution=institution)
    before = {str(r.pk): r for r in membership.roles.all()}
    after = {str(r.pk): r for r in roles}
    changed_master = any(
        r.is_master for k, r in {**before, **after}.items() if (k in before) != (k in after)
    )
    if changed_master and not user_is_master(actor, institution):
        raise BusinessRuleError("Somente usuários MASTER podem conceder ou retirar o perfil MASTER.")
    if user.pk == actor.pk and changed_master:
        raise BusinessRuleError("Você não pode alterar o seu próprio perfil MASTER.")
    MembershipRole.objects.filter(membership=membership).exclude(role_id__in=after.keys()).delete()
    for key, role in after.items():
        MembershipRole.objects.get_or_create(membership=membership, role=role)
    if set(before) != set(after):
        log_event(
            AuditAction.PERMISSION_CHANGE, module="admin.usuarios", obj=user,
            old={"perfis": sorted(r.code for r in before.values())},
            new={"perfis": sorted(r.code for r in after.values())},
            institution_id=institution.pk,
        )
    return membership


# ---------------------------------------------------------------------------
# Login / bloqueio
# ---------------------------------------------------------------------------
def register_login_failure(user: User | None, username: str, reason: str) -> None:
    if user is not None:
        user.failed_login_attempts += 1
        extra_lock = None
        if user.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            user.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            extra_lock = user.locked_until.isoformat()
        User.objects.filter(pk=user.pk).update(
            failed_login_attempts=user.failed_login_attempts, locked_until=user.locked_until
        )
        log_event(
            AuditAction.LOGIN_FAILED, module="acesso", obj=user, user=user,
            extra={"motivo": reason, "tentativas": user.failed_login_attempts, "bloqueado_ate": extra_lock},
            institution_id=user.default_institution_id,
        )
    else:
        log_event(
            AuditAction.LOGIN_FAILED, module="acesso", username=username[:150],
            object_type="accounts.user", extra={"motivo": reason},
        )


def register_login_success(user: User, ip: str | None) -> None:
    User.objects.filter(pk=user.pk).update(
        failed_login_attempts=0, locked_until=None, last_login=timezone.now(), last_login_ip=ip,
    )
    log_event(AuditAction.LOGIN, module="acesso", obj=user, user=user,
              institution_id=user.default_institution_id)
