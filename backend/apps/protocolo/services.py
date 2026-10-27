"""Regras do Protocolo: numeração, tramitação, sobrestamento e prazos."""
from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import has_perm
from apps.core.exceptions import BusinessRuleError

from . import deadlines
from .models import (
    OPEN_STATUSES, Holiday, Movement, MovementKind, Process, ProcessStatus, ProtocolCounter, Sector,
)

MANAGER_PERMISSION = "protocolo.configuracao:editar"


def holidays_for(institution) -> frozenset:
    return frozenset(Holiday.objects.filter(institution=institution, active=True).values_list("date", flat=True))


def is_manager(request) -> bool:
    return has_perm(request, MANAGER_PERMISSION)


def user_sectors(user, institution):
    return Sector.objects.filter(institution=institution, members=user, active=True)


def require_sector_member(request, sector: Sector):
    """Somente quem pertence ao setor (ou o gestor do protocolo) movimenta processos ali."""
    if is_manager(request):
        return
    if not sector.members.filter(pk=request.user.pk).exists():
        raise BusinessRuleError(f"Você não pertence ao setor {sector.code}, onde o processo se encontra.")


def _require_open(process: Process, allow_suspended=False):
    allowed = OPEN_STATUSES if allow_suspended else [ProcessStatus.EM_TRAMITACAO]
    if process.status not in allowed:
        raise BusinessRuleError(f"Operação não permitida: processo {process.get_status_display().lower()}.")


def _move(process, kind, text="", from_sector=None, to_sector=None):
    return Movement.objects.create(
        institution_id=process.institution_id, process=process, kind=kind, text=text,
        from_sector=from_sector, to_sector=to_sector, occurred_at=timezone.now(), due_date_after=process.due_date,
    )


def _require_text(text: str, what: str = "o despacho"):
    if not text or len(text.strip()) < 10:
        raise BusinessRuleError(f"Informe {what} com pelo menos 10 caracteres.")


@transaction.atomic
def open_process(request, *, process_type, sector, subject, interested_name, description="", interested=None,
                 interested_cpf="", priority="NORMAL", external_number="") -> Process:
    institution = request.institution
    """
    Qualquer usuário com permissão no Protocolo abre processos, para qualquer setor ativo. Se quem abre não é do
    setor de destino, o processo chega como "aguardando recebimento" (o prazo do setor conta a partir do recebimento).
    """
    if not process_type.active or not sector.active:
        raise BusinessRuleError("Tipo de processo ou setor inativo.")
    member = is_manager(request) or sector.members.filter(pk=request.user.pk).exists()
    now = timezone.now()
    today = timezone.localdate()
    counter, _ = ProtocolCounter.objects.select_for_update().get_or_create(institution=institution, year=today.year)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    hol = holidays_for(institution)
    process = Process.objects.create(
        institution=institution, number=counter.last_number, year=today.year, process_type=process_type,
        subject=subject, description=description, interested=interested,
        interested_name=interested.name if interested else interested_name,
        interested_cpf=interested.cpf if interested else interested_cpf, priority=priority,
        external_number=external_number, current_sector=sector, opened_at=now, opened_date=today,
        business_days=process_type.business_days, deadline_days=process_type.deadline_days,
        due_date=deadlines.add_days(today, process_type.deadline_days, process_type.business_days, hol),
        sector_due_date=_sector_due(process_type, today, hol) if member else None,
        pending_receipt=not member,
    )
    _move(process, MovementKind.ABERTURA, description or subject, to_sector=sector)
    return process


def _sector_due(process_type, start, hol):
    if not process_type.sector_deadline_days:
        return None
    return deadlines.add_days(start, process_type.sector_deadline_days, process_type.business_days, hol)


@transaction.atomic
def send(request, process: Process, to_sector: Sector, text: str) -> Process:
    _require_open(process)
    if process.pending_receipt:
        raise BusinessRuleError("O processo ainda não foi recebido pelo setor atual.")
    if to_sector.pk == process.current_sector_id:
        raise BusinessRuleError("Escolha um setor diferente do atual.")
    if not to_sector.active or to_sector.institution_id != process.institution_id:
        raise BusinessRuleError("Setor de destino inválido.")
    require_sector_member(request, process.current_sector)
    _require_text(text)
    origin = process.current_sector
    process.current_sector, process.pending_receipt, process.sector_due_date = to_sector, True, None
    process.save()
    _move(process, MovementKind.ENVIO, text, from_sector=origin, to_sector=to_sector)
    return process


@transaction.atomic
def receive(request, process: Process) -> Process:
    _require_open(process, allow_suspended=True)
    if not process.pending_receipt:
        raise BusinessRuleError("Não há envio pendente de recebimento.")
    require_sector_member(request, process.current_sector)
    process.pending_receipt = False
    process.sector_due_date = _sector_due(process.process_type, timezone.localdate(), holidays_for(process.institution))
    process.save()
    _move(process, MovementKind.RECEBIMENTO, to_sector=process.current_sector)
    return process


@transaction.atomic
def dispatch(request, process: Process, text: str) -> Process:
    _require_open(process, allow_suspended=True)
    require_sector_member(request, process.current_sector)
    _require_text(text)
    _move(process, MovementKind.DESPACHO, text, from_sector=process.current_sector)
    return process


@transaction.atomic
def suspend(request, process: Process, text: str) -> Process:
    _require_open(process)
    require_sector_member(request, process.current_sector)
    _require_text(text, "a justificativa do sobrestamento")
    process.status, process.suspended_since = ProcessStatus.SOBRESTADO, timezone.localdate()
    process.save()
    _move(process, MovementKind.SOBRESTAMENTO, text, from_sector=process.current_sector)
    return process


@transaction.atomic
def resume(request, process: Process, text: str) -> Process:
    if process.status != ProcessStatus.SOBRESTADO:
        raise BusinessRuleError("O processo não está sobrestado.")
    require_sector_member(request, process.current_sector)
    _require_text(text, "a justificativa da retomada")
    hol = holidays_for(process.institution)
    paused = deadlines.count_days(process.suspended_since, timezone.localdate(), process.business_days, hol)
    process.due_date = deadlines.add_days(process.due_date, paused, process.business_days, hol)
    if process.sector_due_date:
        process.sector_due_date = deadlines.add_days(process.sector_due_date, paused, process.business_days, hol)
    process.status, process.suspended_since = ProcessStatus.EM_TRAMITACAO, None
    process.save()
    _move(process, MovementKind.RETOMADA, f"{text}\nPrazo estendido em {paused} dia(s) de sobrestamento.",
          from_sector=process.current_sector)
    return process


@transaction.atomic
def extend(request, process: Process, days: int, text: str) -> Process:
    _require_open(process)
    if not is_manager(request):
        raise BusinessRuleError("Somente o gestor do protocolo pode prorrogar prazos.")
    if days < 1 or days > 365:
        raise BusinessRuleError("Informe uma prorrogação entre 1 e 365 dias.")
    _require_text(text, "a justificativa da prorrogação")
    process.due_date = deadlines.add_days(process.due_date, days, process.business_days, holidays_for(process.institution))
    process.deadline_days += days
    process.save()
    _move(process, MovementKind.PRORROGACAO, f"{text}\nProrrogado por {days} dia(s).", from_sector=process.current_sector)
    return process


@transaction.atomic
def close(request, process: Process, text: str, archive: bool) -> Process:
    _require_open(process, allow_suspended=True)
    if process.pending_receipt:
        raise BusinessRuleError("Receba o processo antes de concluí-lo ou arquivá-lo.")
    require_sector_member(request, process.current_sector)
    _require_text(text, "o despacho final")
    process.status = ProcessStatus.ARQUIVADO if archive else ProcessStatus.CONCLUIDO
    process.closed_at, process.suspended_since = timezone.now(), None
    process.save()
    _move(process, MovementKind.ARQUIVAMENTO if archive else MovementKind.CONCLUSAO, text,
          from_sector=process.current_sector)
    return process


@transaction.atomic
def reopen(request, process: Process, text: str) -> Process:
    if process.status not in (ProcessStatus.ARQUIVADO, ProcessStatus.CONCLUIDO):
        raise BusinessRuleError("O processo não está encerrado.")
    if not is_manager(request):
        raise BusinessRuleError("Somente o gestor do protocolo pode desarquivar processos.")
    _require_text(text, "a justificativa do desarquivamento")
    process.status, process.closed_at = ProcessStatus.EM_TRAMITACAO, None
    process.save()
    _move(process, MovementKind.DESARQUIVAMENTO, text, to_sector=process.current_sector)
    return process


def deadline_info(process: Process, hol: frozenset) -> dict:
    today = timezone.localdate()
    if process.status not in OPEN_STATUSES:
        return {"dias_restantes": None, "atrasado": False, "dias_restantes_setor": None}
    ref = process.suspended_since or today  # sobrestado: contagem congelada
    left = deadlines.remaining(process.due_date, ref, process.business_days, hol)
    sector_left = (deadlines.remaining(process.sector_due_date, ref, process.business_days, hol)
                   if process.sector_due_date else None)
    return {"dias_restantes": left, "atrasado": left < 0, "dias_restantes_setor": sector_left}


@transaction.atomic
def generate_national_holidays(institution, year: int) -> int:
    existing = set(Holiday.objects.filter(institution=institution, date__year=year).values_list("date", flat=True))
    new = [Holiday(institution=institution, date=d, name=n, kind=k)
           for d, n, k in deadlines.national_holidays(year) if d not in existing]
    Holiday.objects.bulk_create(new)
    return len(new)
