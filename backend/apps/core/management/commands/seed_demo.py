"""
Dados de DEMONSTRAÇÃO (identificados como DEMO em todas as telas).

    python manage.py seed_demo           # cria alertas DEMO
    python manage.py seed_demo --remove  # remove os alertas DEMO

Os alertas DEMO ilustram pendências de módulos que ainda não existem
(benefícios, prova de vida, eSocial, folha). Eles NUNCA são misturados com
os alertas reais: possuem is_demo=True e selo DEMO na interface.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.alerts.models import Alert, Severity
from apps.core.context import audit_context
from apps.institutions.models import Institution

DEMO_ALERTS = [
    (Severity.CRITICO, "1 evento eSocial S-2410 rejeitado", "esocial.rejeicoes", "/esocial/rejeicoes"),
    (Severity.ATENCAO, "3 benefícios aguardando análise", "concessao.processos", "/concessao/processos"),
    (Severity.ATENCAO, "2 pensionistas com prova de vida pendente", "provadevida.pendentes", "/prova-de-vida/pendentes"),
    (Severity.ATENCAO, "4 beneficiários com dados bancários pendentes", "folha.beneficiarios", "/folha/beneficiarios"),
    (Severity.INFORMATIVO, "Folha da próxima competência ainda não calculada", "folha.calculo", "/folha/calculo"),
]


class Command(BaseCommand):
    help = "Cria (ou remove) alertas de DEMONSTRAÇÃO."

    def add_arguments(self, parser):
        parser.add_argument("--institution", default="PREVIBAM")
        parser.add_argument("--remove", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        inst = Institution.objects.filter(short_name__iexact=opts["institution"]).first()
        if not inst:
            raise CommandError("Instituição não encontrada. Execute seed_initial antes.")
        with audit_context(source="command", justification="Dados de demonstração (seed_demo)"):
            if opts["remove"]:
                n = 0
                for alert in Alert.objects.filter(institution=inst, is_demo=True):
                    alert.delete()
                    n += 1
                self.stdout.write(self.style.SUCCESS(f"{n} alerta(s) DEMO removido(s)."))
                return
            created = 0
            for i, (sev, title, module, link) in enumerate(DEMO_ALERTS):
                _, c = Alert.objects.get_or_create(
                    institution=inst, fingerprint=f"DEMO:{i}", status="ABERTO",
                    defaults={
                        "severity": sev, "code": "DEMO", "module": module, "title": title,
                        "message": "Alerta de DEMONSTRAÇÃO — o módulo de origem ainda não foi implementado.",
                        "link": link, "is_demo": True,
                    },
                )
                created += int(c)
        self.stdout.write(self.style.SUCCESS(f"{created} alerta(s) DEMO criado(s)."))
