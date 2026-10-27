from django.core.management.base import BaseCommand, CommandError

from apps.institutions.models import Institution

from ...defaults import seed_financeiro


class Command(BaseCommand):
    help = "Parâmetros da arrecadação: alíquota patronal e dia de vencimento das contribuições."

    def add_arguments(self, parser):
        parser.add_argument("--institution", required=True, help="Sigla da instituição (ex.: PREVIBAM)")

    def handle(self, *args, **opts):
        inst = Institution.objects.filter(short_name__iexact=opts["institution"]).first()
        if inst is None:
            raise CommandError("Instituição não encontrada.")
        created = seed_financeiro(inst)
        self.stdout.write(self.style.SUCCESS(f"Parâmetros criados: {', '.join(created) or 'nenhum'}."))