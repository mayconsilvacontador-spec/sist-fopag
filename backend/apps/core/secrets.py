"""Criptografia de segredos guardados no banco (chave de API etc.). A chave fica no .env do servidor (SIST_SECRETS_KEY)."""
from django.conf import settings

from apps.core.exceptions import BusinessRuleError


def _fernet():
    from cryptography.fernet import Fernet

    key = getattr(settings, "SIST_SECRETS_KEY", "")
    if not key:
        raise BusinessRuleError("Chave de criptografia de segredos não configurada no servidor (SIST_SECRETS_KEY no .env).")
    return Fernet(key.encode())


def encrypt(text: str) -> bytes:
    return _fernet().encrypt(text.encode("utf-8"))


def decrypt(data: bytes) -> str:
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(bytes(data)).decode("utf-8")
    except InvalidToken:
        raise BusinessRuleError("Não foi possível abrir o segredo guardado (a chave do servidor mudou?). Cadastre-o de novo.")
