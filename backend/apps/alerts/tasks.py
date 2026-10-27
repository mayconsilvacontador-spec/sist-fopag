import logging

from celery import shared_task

logger = logging.getLogger("sist")


@shared_task(name="apps.alerts.tasks.run_alert_checks_all")
def run_alert_checks_all():
    """Executa as verificações de alertas para todas as instituições ativas."""
    from apps.core.context import audit_context
    from apps.institutions.models import Institution

    from .services import run_checks

    result = {}
    with audit_context(source="celery"):
        for inst in Institution.objects.filter(active=True):
            result[inst.short_name] = run_checks(inst)
    logger.info("Verificação de alertas concluída: %s", result)
    return result


@shared_task(name="apps.alerts.tasks.run_alert_checks_institution")
def run_alert_checks_institution(institution_id: str):
    from apps.core.context import audit_context
    from apps.institutions.models import Institution

    from .services import run_checks

    with audit_context(source="celery"):
        return run_checks(Institution.objects.get(pk=institution_id))
