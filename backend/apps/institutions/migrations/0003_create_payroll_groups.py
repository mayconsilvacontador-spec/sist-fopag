"""Cria as folhas Financeira e Previdenciária para as instituições já cadastradas."""
import uuid

from django.db import migrations

GROUPS = [
    ("FINANCEIRO", "FINANCEIRO", "FIN", "Folha do Plano Financeiro"),
    ("PREVIDENCIARIO", "PREVIDENCIARIO", "PREV", "Folha do Plano Previdenciário"),
]


def forwards(apps, schema_editor):
    Institution = apps.get_model("institutions", "Institution")
    BenefitPlan = apps.get_model("institutions", "BenefitPlan")
    PayrollGroup = apps.get_model("institutions", "PayrollGroup")
    for inst in Institution.objects.all():
        for segment, kind, code, name in GROUPS:
            if PayrollGroup.objects.filter(institution=inst, segment=segment).exists():
                continue
            plan = BenefitPlan.objects.filter(institution=inst, kind=kind, active=True).order_by("code").first()
            if plan:
                PayrollGroup.objects.create(
                    id=uuid.uuid4(), institution=inst, segment=segment, code=code, name=name, plan=plan,
                )


class Migration(migrations.Migration):
    dependencies = [("institutions", "0002_institution_ibge_code_and_more")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
