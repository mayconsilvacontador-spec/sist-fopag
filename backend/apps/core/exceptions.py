"""Tratamento padronizado de erros da API."""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

logger = logging.getLogger("sist")


class BusinessRuleError(Exception):
    """Violação de regra de negócio (ex.: competência fechada)."""

    def __init__(self, message: str, code: str = "regra_negocio"):
        super().__init__(message)
        self.message = message
        self.code = code


def sist_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        exc = ValidationError(detail=detail)

    if isinstance(exc, (BusinessRuleError, ProtectedError, IntegrityError)):
        # Garante o rollback da transação (ATOMIC_REQUESTS)
        set_rollback()

    if isinstance(exc, BusinessRuleError):
        return Response(
            {"detail": exc.message, "code": exc.code},
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, ProtectedError):
        return Response(
            {
                "detail": "Este registro não pode ser excluído porque possui "
                          "vínculos com outros registros. Inative-o.",
                "code": "registro_protegido",
            },
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, IntegrityError):
        logger.warning("Violação de integridade: %s", exc.__class__.__name__)
        return Response(
            {"detail": "Operação viola uma regra de integridade dos dados (registro duplicado ou referência inválida).",
             "code": "integridade"},
            status=status.HTTP_409_CONFLICT,
        )

    return exception_handler(exc, context)
