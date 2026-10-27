"""Sinais que geram auditoria automática para os modelos registrados."""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import AuditAction
from .registry import get_config
from .services import diff, log_event, snapshot


@receiver(pre_save, dispatch_uid="sist_audit_pre_save")
def _audit_pre_save(sender, instance, raw=False, **kwargs):
    if raw or get_config(sender) is None:
        return
    if instance._state.adding or instance.pk is None:
        instance._audit_old = None
        return
    try:
        old = sender._default_manager.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._audit_old = None
        return
    old_snap = snapshot(old)
    # Detecta troca de senha sem gravar o hash
    if hasattr(old, "password") and old.password != getattr(instance, "password", None):
        old_snap["password"] = "[anterior]"
    instance._audit_old = old_snap


@receiver(post_save, dispatch_uid="sist_audit_post_save")
def _audit_post_save(sender, instance, created, raw=False, **kwargs):
    config = get_config(sender)
    if raw or config is None:
        return
    new_snap = snapshot(instance)
    if created:
        log_event(AuditAction.CREATE, module=config.module, obj=instance, new=new_snap)
        return
    old_snap = getattr(instance, "_audit_old", None)
    if old_snap is None:
        return
    if old_snap.get("password") == "[anterior]":
        new_snap["password"] = "[alterada]"
    changed_old, changed_new = diff(old_snap, new_snap)
    if changed_new:
        log_event(AuditAction.UPDATE, module=config.module, obj=instance,
                  old=changed_old, new=changed_new)
    instance._audit_old = None


@receiver(post_delete, dispatch_uid="sist_audit_post_delete")
def _audit_post_delete(sender, instance, **kwargs):
    config = get_config(sender)
    if config is None:
        return
    log_event(AuditAction.DELETE, module=config.module, obj=instance, old=snapshot(instance))
