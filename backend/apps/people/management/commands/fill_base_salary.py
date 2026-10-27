"""
Preenche o vencimento base dos vínculos importados da base SPREV que ficaram sem valor (versões antigas do
importador ignoravam VL_BASE_CALCULO). Lê os arquivos de SERVIDORES guardados nos lotes; nunca sobrescreve
um vencimento já informado.

    manage.py fill_base_salary --institution PREVIBAM [--dry-run]
"""
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.services import log_event
from apps.core.validators import only_digits
from apps.employment.models import EmploymentLink
from apps.institutions.models import Institution
from apps.people.importers.sprev import _dec, _s, detect_kind, read_table
from apps.people.models import ImportBatch


class Command(BaseCommand):
    help = "Preenche o vencimento base dos vínculos importados a partir dos arquivos de SERVIDORES dos lotes."

    def add_arguments(self, parser):
        parser.add_argument("--institution", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        inst = Institution.objects.filter(short_name=opts["institution"]).first()
        if inst is None:
            raise CommandError("Instituição não encontrada.")
        values = {}
        for batch in ImportBatch.objects.filter(institution=inst).order_by("created_at"):
            for f in batch.files or []:
                path = f.get("caminho")
                if not path or not default_storage.exists(path):
                    continue
                with default_storage.open(path, "rb") as fh:
                    rows = read_table(fh.read(), f.get("nome") or path)
                if detect_kind(rows) != "servidores":
                    continue
                for row in rows:
                    reg = only_digits(_s(row.get("ID_SERVIDOR_MATRICULA")).split(".")[0]) or _s(row.get("ID_SERVIDOR_MATRICULA"))
                    val = _dec(row.get("VL_BASE_CALCULO")) or _dec(row.get("VL_REMUNERACAO"))
                    cpf = only_digits(_s(row.get("ID_SERVIDOR_CPF"))).zfill(11)
                    if reg and val:
                        values[(cpf, reg)] = val
        done = 0
        with transaction.atomic():
            for link in EmploymentLink.objects.filter(institution=inst, base_salary__isnull=True).select_related("person"):
                val = values.get((link.person.cpf, link.registration))
                if val is None:
                    continue
                done += 1
                if not opts["dry_run"]:
                    link.base_salary = val
                    link.save(update_fields=["base_salary", "updated_at"])
            if done and not opts["dry_run"]:
                log_event("UPDATE", module="cadastros.vinculos", object_repr=f"Vencimento base preenchido em {done} vínculo(s) pela base importada")
        self.stdout.write(f"Vínculos {'a preencher' if opts['dry_run'] else 'preenchidos'}: {done} "
                          f"(valores encontrados nos arquivos: {len(values)}).")
