from .models import DEFAULT_BANKS, Bank


def ensure_default_banks(institution) -> None:
    """Carga inicial dos principais bancos (somente se a instituição ainda não tem nenhum)."""
    if Bank.objects.filter(institution=institution).exists():
        return
    Bank.objects.bulk_create([Bank(institution=institution, code=c, name=n) for c, n in DEFAULT_BANKS])
