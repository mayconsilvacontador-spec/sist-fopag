"""
Alíquotas de contribuição ao RPPS com vigência (servidor e patronal), guardadas nos parâmetros versionados
(`folha.aliquota_segurado` e `arrecadacao.aliquota_patronal`). Diferente de `set_parameter`, aceita também incluir
uma vigência ANTERIOR à primeira cadastrada (histórico, ex.: 11% até 08/2025), para o controle da contribuição e a
ficha financeira de anos passados. Nada é apagado: vigência nova encerra a anterior; vigência no meio do histórico
é recusada (evita sobrepor períodos).
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

KEYS = {
    "SERVIDOR": ("folha.aliquota_segurado", "Contribuição do servidor ativo, aposentado e pensionista"),
    "PATRONAL": ("arrecadacao.aliquota_patronal", "Contribuição patronal (ente/órgão)"),
}


def _pct(value) -> Decimal:
    try:
        v = Decimal(str(value).replace("%", "").replace(",", ".").strip())
    except InvalidOperation:
        raise BusinessRuleError("Alíquota inválida.")
    if not Decimal("0") < v <= Decimal("50"):
        raise BusinessRuleError("Informe a alíquota em percentual (ex.: 14 ou 11,5).")
    return v


def _fmt(rate) -> str:
    """0.14 -> '14'; 0.115 -> '11.5' (sem notação científica)."""
    txt = f"{(Decimal(str(rate)) * 100).quantize(Decimal('0.01')):f}"
    return txt.rstrip("0").rstrip(".") if "." in txt else txt


def listing(institution) -> list[dict]:
    from apps.institutions.models import Parameter

    out = []
    for kind, (key, label) in KEYS.items():
        versions = Parameter.objects.filter(institution=institution, key=key).order_by("-valid_from")
        out.append({"tipo": kind, "chave": key, "descricao": label, "vigencias": [
            {"inicio": p.valid_from, "fim": p.valid_to, "percentual": _fmt(p.value),
             "fundamento": p.description, "motivo": p.change_reason, "versao": p.version} for p in versions]})
    return out


def rates_on(institution, on) -> dict:
    from apps.institutions.services import get_parameter

    out = {}
    for kind, (key, _) in KEYS.items():
        v = get_parameter(institution, key, on)
        out[kind.lower()] = _fmt(v) if v not in (None, "") else None
    return out


@transaction.atomic
def add_version(institution, kind: str, percent, valid_from, legal_basis: str, reason: str):
    from apps.institutions.models import Parameter
    from apps.institutions.services import set_parameter

    if kind not in KEYS:
        raise BusinessRuleError("Tipo de alíquota inválido.")
    key, _ = KEYS[kind]
    rate = (_pct(percent) / 100).quantize(Decimal("0.0001"))
    valid_from = valid_from.replace(day=1)
    if not legal_basis.strip():
        raise BusinessRuleError("Informe o fundamento legal (lei, emenda ou decreto).")
    versions = Parameter.objects.select_for_update().filter(institution=institution, key=key)
    first = versions.order_by("valid_from").first()
    if first is not None and valid_from < first.valid_from:
        # vigência histórica, antes da primeira cadastrada: termina no dia anterior ao início da primeira
        p = Parameter.objects.create(
            institution=institution, key=key, value=str(rate), valid_from=valid_from,
            valid_to=first.valid_from - timedelta(days=1), description=legal_basis[:255],
            version=(versions.order_by("-version").first().version + 1), change_reason=reason or "Inclusão de vigência histórica")
    elif first is not None and versions.filter(valid_from__gte=valid_from).exists():
        raise BusinessRuleError("Já existe vigência começando nesta data ou depois. Só é possível incluir vigência "
                                "nova (depois da última) ou histórica (antes da primeira).")
    else:
        p = set_parameter(institution, key, str(rate), valid_from, description=legal_basis[:255],
                          change_reason=reason or ("Nova alíquota" if first else ""))
    log_event("CREATE", module="arrecadacao.aliquotas", obj=p,
              object_repr=f"Alíquota {kind.lower()} {_fmt(rate)}% desde {valid_from:%m/%Y} ({legal_basis[:80]})")
    return p
