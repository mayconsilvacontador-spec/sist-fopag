from django.db import transaction
from django.utils import timezone

from apps.core.context import audit_context
from apps.core.exceptions import BusinessRuleError

from .checks import CHECKS
from .models import Alert, AlertStatus


@transaction.atomic
def run_checks(institution) -> dict:
    """
    Executa todas as verificações para a instituição. Cria alertas novos,
    atualiza os existentes e resolve automaticamente os que deixaram de
    ocorrer. Alertas DEMO não são afetados.
    """
    stats = {"criados": 0, "mantidos": 0, "resolvidos": 0}
    now = timezone.now()
    with audit_context(source="system", justification=""):
        for code, fn in CHECKS.items():
            specs = fn(institution)
            seen = set()
            for spec in specs:
                fingerprint = f"{code}:{spec.key}"[:200]
                seen.add(fingerprint)
                alert = Alert.objects.filter(
                    institution=institution, fingerprint=fingerprint, status=AlertStatus.ABERTO
                ).first()
                if alert:
                    Alert.objects.filter(pk=alert.pk).update(
                        last_seen_at=now, title=spec.title, message=spec.message, severity=spec.severity
                    )
                    stats["mantidos"] += 1
                else:
                    Alert.objects.create(
                        institution=institution, severity=spec.severity, code=code,
                        module=spec.module, title=spec.title, message=spec.message, link=spec.link,
                        object_type=spec.object_type, object_id=spec.object_id, fingerprint=fingerprint,
                    )
                    stats["criados"] += 1
            stale = Alert.objects.filter(
                institution=institution, code=code, status=AlertStatus.ABERTO, is_demo=False
            ).exclude(fingerprint__in=seen)
            for alert in stale:
                alert.status = AlertStatus.RESOLVIDO
                alert.resolved_at = now
                alert.resolution_note = "Resolvido automaticamente: a inconsistência não foi mais encontrada."
                alert.save()
                stats["resolvidos"] += 1
    return stats


@transaction.atomic
def resolve_alert(alert: Alert, user, note: str, discard: bool = False) -> Alert:
    if alert.status != AlertStatus.ABERTO:
        raise BusinessRuleError("O alerta já está encerrado.")
    if not note or len(note.strip()) < 5:
        raise BusinessRuleError("Informe uma observação para encerrar o alerta.")
    alert.status = AlertStatus.DESCARTADO if discard else AlertStatus.RESOLVIDO
    alert.resolved_at = timezone.now()
    alert.resolved_by = user
    alert.resolution_note = note.strip()
    alert.save()
    return alert
