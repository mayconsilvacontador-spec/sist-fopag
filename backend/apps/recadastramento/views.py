import json

from django.db.models import Q
from django.http import FileResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import has_perm
from apps.core.validators import only_digits
from apps.core.views import InstitutionScopedMixin

from . import services
from .models import Channel, RegistrationCampaign, Reregistration
from .serializers import CampaignSerializer, ItemSerializer

GROUP_MODULE = {"SERVIDOR": "recadastramento.segurados", "BENEFICIARIO": "recadastramento.beneficiarios"}


def _need(request, perm, what):
    if not has_perm(request, perm):
        raise PermissionDenied(f"Seu perfil não tem permissão para {what}.")


def _json(v):
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v or "{}")
    except ValueError:
        raise serializers.ValidationError("Dados inválidos.")


class CampaignViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, viewsets.GenericViewSet):
    module_code = "recadastramento.campanhas"
    serializer_class = CampaignSerializer
    queryset = RegistrationCampaign.objects.select_related("organ")
    action_permissions = {"open": "editar", "refresh": "editar", "close": "fechar"}

    def perform_create(self, serializer):
        services.validate(RegistrationCampaign(**serializer.validated_data))
        serializer.save(institution=self.get_institution())

    def perform_update(self, serializer):
        services.validate(serializer.save())

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        c = self.get_object()
        n = services.open_campaign(c, request.user)
        return Response({**CampaignSerializer(c).data, "incluidos": n})

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        c = self.get_object()
        return Response({**CampaignSerializer(c).data, "incluidos": services.refresh(c)})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return Response(CampaignSerializer(services.close_campaign(self.get_object(), request.user)).data)


class ItemViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """?grupo=SERVIDOR|BENEFICIARIO &situacao=… &campanha= &search= · approve · give-back · presential · file"""

    serializer_class = ItemSerializer
    queryset = Reregistration.objects.select_related("person", "campaign", "reviewed_by")
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {a: "visualizar" for a in ("approve", "give_back", "presential", "file")}

    @property
    def module_code(self):
        return GROUP_MODULE.get(self.request.query_params.get("grupo") or "", "recadastramento.segurados")

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("grupo"):
            qs = qs.filter(group=p["grupo"])
        if p.get("situacao"):
            qs = qs.filter(status__in=p["situacao"].split(","))
        if p.get("campanha"):
            qs = qs.filter(campaign_id=p["campanha"])
        term = (p.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(person__name__icontains=term)
            if digits:
                cond |= Q(person__cpf__startswith=digits)
            qs = qs.filter(cond)
        return qs.order_by("-submitted_at", "person__name") if "ENVIADO" in (p.get("situacao") or "") else qs

    def _check(self, request, item, act="aprovar"):
        _need(request, f"{GROUP_MODULE[item.group]}:{act}", "conferir recadastramentos deste grupo")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        item = self.get_object()
        self._check(request, item)
        return Response(ItemSerializer(services.approve(item, request.user, request.data.get("note", ""))).data)

    @action(detail=True, methods=["post"], url_path="give-back")
    def give_back(self, request, pk=None):
        item = self.get_object()
        self._check(request, item)
        return Response(ItemSerializer(services.give_back(item, request.user, request.data.get("reason", ""))).data)

    @action(detail=True, methods=["post"])
    def presential(self, request, pk=None):
        """Atendimento presencial: a equipe preenche com o segurado e aprova na hora."""
        item = self.get_object()
        self._check(request, item)
        services.submit(item, _json(request.data.get("dados")), _json(request.data.get("declaracoes")),
                        residence=request.FILES.get("comprovante"), id_doc=request.FILES.get("documento"),
                        channel=Channel.PRESENCIAL, user=request.user)
        item.refresh_from_db()
        return Response(ItemSerializer(item).data)

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        item = self.get_object()
        f = item.id_document if request.query_params.get("tipo") == "documento" else item.residence_proof
        if not f:
            raise serializers.ValidationError("Arquivo não enviado.")
        ext = f.name.rsplit(".", 1)[-1].lower()
        return FileResponse(f.open("rb"), content_type={"pdf": "application/pdf", "png": "image/png"}.get(ext, "image/jpeg"))

    @action(detail=True, methods=["get"])
    def cadastro(self, request, pk=None):
        """Dados atuais do cadastro (para o atendimento presencial)."""
        return Response(services.snapshot(self.get_object().person))
