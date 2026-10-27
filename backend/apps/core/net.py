"""Utilitários de rede."""
import ipaddress

from django.conf import settings


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def get_client_ip(request) -> str | None:
    """
    Retorna o IP real do cliente.

    O cabeçalho X-Forwarded-For só é considerado quando a conexão vem de um
    proxy confiável (TRUSTED_PROXY_IPS, ex.: o BFF Next.js). Isso impede que um
    cliente falsifique o IP registrado na auditoria.
    """
    remote = request.META.get("REMOTE_ADDR")
    trusted = set(getattr(settings, "TRUSTED_PROXY_IPS", []))
    if remote in trusted:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            if _valid_ip(candidate):
                return candidate
    return remote if remote and _valid_ip(remote) else None
