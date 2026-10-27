"""Mixins de views reutilizáveis."""
from urllib.parse import unquote

from rest_framework.exceptions import PermissionDenied


class InstitutionScopedMixin:
    """
    Restringe o queryset à instituição corrente (request.institution) e
    preenche a instituição automaticamente na inclusão.
    """

    institution_field = "institution"

    def get_institution(self):
        institution = getattr(self.request, "institution", None)
        if institution is None:
            raise PermissionDenied("Instituição não definida para o usuário.")
        return institution

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(**{self.institution_field: self.get_institution()})

    def perform_create(self, serializer):
        serializer.save(**{self.institution_field: self.get_institution()})


def get_justification(request) -> str:
    # O frontend envia o cabeçalho codificado (encodeURIComponent), como o RequestContextMiddleware espera
    header = unquote(request.headers.get("X-Justification") or "")
    return (request.data.get("justification") or header or "").strip()
