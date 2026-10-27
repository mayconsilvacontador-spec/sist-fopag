from django.core.management.base import BaseCommand

from apps.accounts.services import sync_permissions


class Command(BaseCommand):
    help = "Sincroniza módulos, permissões e perfis de sistema a partir do catálogo (catalog.py)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-roles", action="store_true",
            help="Restaura as permissões padrão de TODOS os perfis de sistema (descarta personalizações).",
        )

    def handle(self, *args, **options):
        stats = sync_permissions(verbose=False, reset_roles=options["reset_roles"])
        self.stdout.write(self.style.SUCCESS(
            f"Catálogo sincronizado: {stats['modules']} módulos, "
            f"{stats['permissions']} novas permissões, {stats['roles']} novos perfis."
        ))
