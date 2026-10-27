"""Serviço central de gravação de auditoria."""
import datetime
import decimal
import logging
import uuid

from django.db import models
from django.db.models.fields.files import FieldFile
from django.utils import timezone

from apps.core.context import get_context

from .models import AuditLog
from .registry import REDACTED_MARK, get_config

logger = logging.getLogger("sist")


def _serialize_value(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, float):  # não deveria ocorrer em campos financeiros
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, FieldFile):
        return value.name or None
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def snapshot(instance) -> dict:
    """Retrato dos campos concretos do registro (FK como ID)."""
    config = get_config(type(instance))
    exclude = config.exclude if config else set()
    redact = config.redact if config else {"password"}
    data = {}
    for f in instance._meta.concrete_fields:
        if f.name in exclude:
            continue
        key = f.attname if isinstance(f, models.ForeignKey) else f.name
        if f.name in redact:
            data[f.name] = REDACTED_MARK if getattr(instance, f.attname) else None
            continue
        data[key] = _serialize_value(getattr(instance, f.attname))
    return data


def diff(old: dict, new: dict) -> tuple[dict, dict]:
    changed_old, changed_new = {}, {}
    for key in set(old) | set(new):
        if old.get(key) != new.get(key):
            changed_old[key] = old.get(key)
            changed_new[key] = new.get(key)
    # Senha: o valor redigido é igual antes e depois; detecta pela flag
    return changed_old, changed_new


def _institution_id_for(obj, explicit=None):
    if explicit:
        return explicit
    if obj is not None:
        inst_id = getattr(obj, "institution_id", None)
        if inst_id:
            return inst_id
        if obj.__class__.__name__ == "Institution":
            return obj.pk
    ctx_inst = get_context().institution_id
    try:
        return uuid.UUID(str(ctx_inst)) if ctx_inst else None
    except ValueError:
        return None


def log_event(
    action: str,
    module: str = "",
    obj=None,
    *,
    object_type: str = "",
    object_id: str = "",
    object_repr: str = "",
    old=None,
    new=None,
    justification: str | None = None,
    user=None,
    username: str = "",
    institution_id=None,
    extra: dict | None = None,
) -> AuditLog:
    """Grava um evento de auditoria usando o contexto da requisição."""
    ctx = get_context()
    user = user if user is not None else ctx.user
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    if obj is not None:
        object_type = object_type or f"{obj._meta.app_label}.{obj._meta.model_name}"
        object_id = object_id or str(obj.pk)
        object_repr = object_repr or str(obj)[:255]
    return AuditLog.objects.create(
        timestamp=timezone.now(),
        institution_id=_institution_id_for(obj, institution_id),
        user=user,
        username=(username or (user.get_username() if user else ""))[:150],
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        source=ctx.source,
        action=action,
        module=module,
        object_type=object_type,
        object_id=object_id,
        object_repr=object_repr[:255],
        old_values=old,
        new_values=new,
        justification=justification if justification is not None else ctx.justification,
        extra=extra,
    )
