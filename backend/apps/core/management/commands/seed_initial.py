"""
Carga inicial (NÃO é dado de demonstração): cria a instituição PREVIBAM,
os planos Financeiro e Previdenciário, o exercício corrente e a
competência de referência.

    python manage.py seed_initial
    python manage.py seed_initial --reference 09/2026

Dados cadastrais que o sistema não conhece (CNPJ, endereço, lei de
segregação) ficam em branco para preenchimento em Administração ›
Instituição. Nenhum valor é inventado.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.services import sync_permissions
from apps.alerts.services import run_checks
from apps.core.context import audit_context
from apps.institutions.models import BenefitPlan, Competence, FiscalYear, Institution, PlanKind
from apps.institutions.services import ensure_payroll_groups, set_reference_competence


class Command(BaseCommand):
    help = "Carga inicial: instituição PREVIBAM, planos, exercício e competência de referência."

    def add_arguments(self, parser):
        parser.add_argument("--reference", help="Competência de referência MM/AAAA (padrão: mês anterior).")

    @transaction.atomic
    def handle(self, *args, **opts):
        sync_permissions(verbose=False)
        today = timezone.localdate()
        if opts.get("reference"):
            try:
                month, year = (int(x) for x in opts["reference"].split("/"))
                assert 1 <= month <= 12
            except Exception:
                raise CommandError("Use o formato MM/AAAA em --reference.")
        else:
            year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)

        with audit_context(source="command", justification="Carga inicial do sistema (seed_initial)"):
            inst, created = Institution.objects.get_or_create(
                short_name="PREVIBAM",
                defaults={
                    "name": "Instituto de Previdência Social dos Servidores Públicos do Município de Barra Mansa",
                    "ente_name": "Município de Barra Mansa",
                    "city": "Barra Mansa",
                    "uf": "RJ",
                },
            )
            self.stdout.write(f"Instituição PREVIBAM {'criada' if created else 'já existente'}.")

            for code, name, kind in (
                ("FIN", "Plano Financeiro", PlanKind.FINANCEIRO),
                ("PREV", "Plano Previdenciário", PlanKind.PREVIDENCIARIO),
            ):
                _, c = BenefitPlan.objects.get_or_create(
                    institution=inst, code=code, defaults={"name": name, "kind": kind}
                )
                self.stdout.write(f"  Plano {code} {'criado' if c else 'já existente'}.")
            ensure_payroll_groups(inst)

            years = {year, today.year}
            for y in sorted(years):
                FiscalYear.objects.get_or_create(institution=inst, year=y)
            fy = FiscalYear.objects.get(institution=inst, year=year)
            comp, _ = Competence.objects.get_or_create(
                institution=inst, year=year, month=month, defaults={"fiscal_year": fy}
            )
            # Competência seguinte (em elaboração)
            ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
            nfy, _ = FiscalYear.objects.get_or_create(institution=inst, year=ny)
            Competence.objects.get_or_create(institution=inst, year=ny, month=nm, defaults={"fiscal_year": nfy})
            set_reference_competence(comp)
            self.stdout.write(f"  Competência de referência: {comp}.")

            stats = run_checks(inst)
            self.stdout.write(f"  Verificação de alertas: {stats}.")

        self.stdout.write(self.style.SUCCESS("Carga inicial concluída."))
