from django.core.management.base import BaseCommand, CommandError

from apps.institutions.models import Institution
from apps.institutions.services import ensure_payroll_groups

from ...defaults import seed_payroll


class Command(BaseCommand):
    help = "Carga inicial da folha: rubricas padrão, tabelas do IRRF, alíquota e margem consignável."

    def add_arguments(self, parser):
        parser.add_argument("--institution", required=True, help="Sigla/código da instituição (ex.: PREVIBAM)")

    def handle(self, *args, **opts):
        inst = Institution.objects.filter(short_name__iexact=opts["institution"]).first()
        if inst is None:
            raise CommandError("Instituição não encontrada.")
        ensure_payroll_groups(inst)
        result = seed_payroll(inst)
        self.stdout.write(self.style.SUCCESS(
            f"Rubricas criadas: {result['rubricas']}. Parâmetros criados: {', '.join(result['parametros']) or 'nenhum'}."))
        self.stdout.write("ATENÇÃO: confira a tabela do IRRF de 2026 (Lei 15.270/2025) em Administração › Parâmetros.")
