from django.core.management.base import BaseCommand

from apps.alerts.services import run_checks
from apps.core.context import audit_context
from apps.institutions.models import Institution


class Command(BaseCommand):
    help = "Executa as verificações da Central de Alertas (equivalente à tarefa periódica do Celery)."

    def handle(self, *args, **opts):
        with audit_context(source="command"):
            for inst in Institution.objects.filter(active=True):
                stats = run_checks(inst)
                self.stdout.write(f"{inst.short_name}: {stats}")
        self.stdout.write(self.style.SUCCESS("Verificação concluída."))
