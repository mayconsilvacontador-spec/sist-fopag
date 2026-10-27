from django.core.management.base import BaseCommand, CommandError

from apps.institutions.models import Institution

from ...defaults import seed_esocial


class Command(BaseCommand):
    help = "Parâmetros do eSocial e sugestões de incidências das rubricas (preenche só campos vazios)."

    def add_arguments(self, parser):
        parser.add_argument("--institution", required=True, help="Sigla da instituição (ex.: PREVIBAM)")

    def handle(self, *args, **opts):
        inst = Institution.objects.filter(short_name__iexact=opts["institution"]).first()
        if inst is None:
            raise CommandError("Instituição não encontrada.")
        r = seed_esocial(inst)
        self.stdout.write(self.style.SUCCESS(
            f"Rubricas com incidências sugeridas: {r['rubricas_atualizadas']}. "
            f"Parâmetros criados: {', '.join(r['parametros']) or 'nenhum'}."))
        self.stdout.write("ATENÇÃO: confira as incidências e informe a natureza (Tabela 03) de cada rubrica.")
