from django.db import transaction
from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.validators import only_digits
from apps.core.views import InstitutionScopedMixin

from .models import EmploymentLink, EventType, FunctionalEvent, LinkStatus
from .serializers import CloseLinkSerializer, EmploymentLinkSerializer, FunctionalEventSerializer

CLOSE_EVENT = {
    LinkStatus.APOSENTADO: EventType.APOSENTADORIA,
    LinkStatus.EXONERADO: EventType.EXONERACAO,
    LinkStatus.FALECIDO: EventType.FALECIMENTO,
    LinkStatus.ENCERRADO: EventType.OUTROS,
}


class EmploymentLinkViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Vínculos. Sem exclusão: encerrar com POST {id}/close/ (gera evento no histórico funcional)."""

    module_code = "cadastros.vinculos"
    serializer_class = EmploymentLinkSerializer
    queryset = EmploymentLink.objects.select_related(
        "person", "organ", "position", "initial_position", "workplace", "life_purchase").all()
    filterset_fields = ["person", "organ", "status", "segment", "situation"]
    ordering_fields = ["registration", "person__name", "position_start"]
    action_permissions = {"close": "editar"}

    def get_queryset(self):
        qs = super().get_queryset()
        term = (self.request.query_params.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(person__name__icontains=term) | Q(registration__icontains=term) | Q(position__name__icontains=term)
            if len(digits) >= 3:
                cond |= Q(person__cpf__startswith=digits)
            qs = qs.filter(cond)
        return qs

    def perform_update(self, serializer):
        if serializer.instance.status != LinkStatus.ATIVO:
            raise BusinessRuleError("Vínculo encerrado não pode ser alterado.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        link = self.get_object()
        if link.status != LinkStatus.ATIVO:
            raise BusinessRuleError("O vínculo já está encerrado.")
        ser = CloseLinkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d["end_date"] < link.position_start:
            raise BusinessRuleError("O encerramento não pode ser anterior ao início no cargo.")
        with transaction.atomic():
            link.status, link.end_date, link.end_reason = d["status"], d["end_date"], d["end_reason"]
            link.save()
            FunctionalEvent.objects.create(
                institution=link.institution, link=link, event_type=CLOSE_EVENT[d["status"]],
                start_date=d["end_date"], act_type=d.get("act_type", ""), act_number=d.get("act_number", ""),
                act_date=d.get("act_date"), publication=d.get("publication", ""), description=d["end_reason"],
            )
        return Response(self.get_serializer(link).data)


class FunctionalEventViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                             mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Histórico funcional do vínculo (?link=<id>). Correções são auditadas; não há exclusão."""

    module_code = "cadastros.vinculos"
    serializer_class = FunctionalEventSerializer
    queryset = FunctionalEvent.objects.select_related("created_by").all()
    filterset_fields = ["link", "event_type"]
    pagination_class = None
    action_permissions = {"create": "editar"}

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list" and not self.request.query_params.get("link"):
            return qs.none()
        return qs
