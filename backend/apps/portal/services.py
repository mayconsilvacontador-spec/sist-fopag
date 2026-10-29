"""Criação de acesso, autenticação e consultas do Portal do Segurado."""
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import only_digits

from .models import PortalAccess, PortalRequest, RequestStatus

_DUMMY = make_password("portal-dummy-password")


@transaction.atomic
def create_access(institution, person) -> tuple[PortalAccess, str]:
    """Cria (ou reativa) o acesso e devolve a senha provisória — exibida UMA vez para entregar ao segurado."""
    from apps.accounts.models import User
    from apps.accounts.serializers import generate_temporary_password

    if person.death_date:
        raise BusinessRuleError("Pessoa com óbito registrado não recebe acesso ao portal.")
    if not person.name:
        raise BusinessRuleError("Complete o nome da pessoa no cadastro antes de criar o acesso.")
    password = generate_temporary_password()
    access = PortalAccess.objects.filter(institution=institution, person=person).select_related("user").first()
    if access:
        user = access.user
        user.is_active, user.must_change_password = True, True
        user.set_password(password)
        user.failed_login_attempts, user.locked_until = 0, None
        user.save()
        access.active = True
        access.save(update_fields=["active", "updated_at"])
        log_event("UPDATE", module="portal", obj=access, object_repr=f"Portal — nova senha provisória ({person.name})")
        return access, password
    user = User.objects.create(
        # CPF não é gravado no usuário (é único entre usuários internos); o vínculo é a pessoa do cadastro
        username=f"portal-{institution.short_name.lower()}-{person.cpf}", full_name=person.name,
        email=person.email or "", is_portal=True, must_change_password=True, default_institution=institution)
    user.set_password(password)
    user.save()
    access = PortalAccess.objects.create(institution=institution, user=user, person=person)
    log_event("CREATE", module="portal", obj=access, object_repr=f"Portal — acesso criado ({person.name})")
    return access, password


@transaction.atomic
def deactivate(access: PortalAccess, justification: str) -> PortalAccess:
    if not justification or len(justification.strip()) < 10:
        raise BusinessRuleError("Informe uma justificativa com pelo menos 10 caracteres.")
    access.active = False
    access.save(update_fields=["active", "updated_at"])
    access.user.is_active = False
    access.user.save(update_fields=["is_active"])
    log_event("UPDATE", module="portal", obj=access, object_repr=f"Portal — acesso bloqueado ({access.person.name})",
              justification=justification)
    return access


def authenticate(cpf: str, password: str):
    """Retorna o PortalAccess autenticado ou None (tempo de resposta equalizado)."""
    from apps.accounts import services as acc_services

    cpf = only_digits(cpf)
    accesses = list(PortalAccess.objects.filter(person__cpf=cpf, active=True, user__is_active=True)
                    .select_related("user", "person", "institution"))
    if not accesses:
        check_password(password, _DUMMY)
        return None, "Usuário ou senha inválidos."
    for acc in accesses:
        user = acc.user
        if user.is_locked:
            minutes = max(1, int((user.locked_until - timezone.now()).total_seconds() // 60) + 1)
            return None, f"Acesso bloqueado por excesso de tentativas. Tente novamente em {minutes} minuto(s)."
        if user.check_password(password):
            acc_services.register_login_success(user, None)
            PortalAccess.objects.filter(pk=acc.pk).update(last_access=timezone.now())
            return acc, ""
    for acc in accesses:
        acc_services.register_login_failure(acc.user, acc.user.username, "senha_incorreta_portal")
    return None, "Usuário ou senha inválidos."


@transaction.atomic
def answer_request(req: PortalRequest, user, answer: str, status: str, process=None) -> PortalRequest:
    if status not in RequestStatus.values:
        raise BusinessRuleError("Situação inválida.")
    if status == RequestStatus.RESPONDIDA and len((answer or "").strip()) < 5:
        raise BusinessRuleError("Escreva a resposta ao segurado.")
    req.status, req.answer = status, (answer or "").strip()
    if status == RequestStatus.RESPONDIDA:
        req.answered_by, req.answered_at = user, timezone.now()
    if process is not None:
        req.process = process
    req.save()
    log_event("UPDATE", module="portal", obj=req, object_repr=f"Portal — solicitação {req.get_status_display().lower()}")
    if status == RequestStatus.RESPONDIDA:
        from .notifications import notify

        notify(req.person, f"req:{req.pk}:respondida", "Sua solicitação foi respondida",
               f"{req.subject}: veja a resposta em Solicitações.", tab="solicitacoes")
    return req
