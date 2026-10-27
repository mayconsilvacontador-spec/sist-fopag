from datetime import date

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
from .models import LifeProof, LifeProofCampaign
from .serializers import CampaignSerializer, ProofSerializer


def _need(request, perm, what):
    if not has_perm(request, perm):
        raise PermissionDenied(f"Seu perfil não tem permissão para {what}.")


class CampaignViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Campanhas (por ato do órgão). Não há exclusão. open/refresh = editar; close = fechar; suspend = Bloqueados:aprovar."""

    module_code = "provadevida.campanhas"
    serializer_class = CampaignSerializer
    queryset = LifeProofCampaign.objects.all()
    action_permissions = {"open": "editar", "refresh": "editar", "close": "fechar", "suspend": "visualizar"}

    def perform_create(self, serializer):
        services.validate(LifeProofCampaign(**serializer.validated_data))
        serializer.save(institution=self.get_institution())

    def perform_update(self, serializer):
        obj = serializer.save()
        services.validate(obj)

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        c = self.get_object()
        n = services.open_campaign(c, request.user)
        return Response({**CampaignSerializer(c).data, "incluidos": n})

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        c = self.get_object()
        n = services.refresh(c)
        return Response({**CampaignSerializer(c).data, "incluidos": n})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return Response(CampaignSerializer(services.close_campaign(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        _need(request, "provadevida.bloqueados:aprovar", "suspender benefícios")
        c = self.get_object()
        out = services.suspend_overdue(c, request.user, request.data.get("password", ""))
        return Response({**CampaignSerializer(c).data, **out})


STATUS_MODULE = {"REALIZADA": "provadevida.realizadas", "DISPENSADA": "provadevida.realizadas",
                 "BLOQUEADO": "provadevida.bloqueados"}


class ProofViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Provas por campanha. ?situacao=PENDENTE|REALIZADA|DISPENSADA|BLOQUEADO (vírgulas) &campanha= &search= &vencidas=1
    register (multipart: done_date, channel, notes, file, password) · waive (notes) · attachment (download)
    """

    serializer_class = ProofSerializer
    queryset = LifeProof.objects.select_related("person", "campaign", "registered_by")
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {"register": "visualizar", "waive": "visualizar", "attachment": "visualizar",
                          "reject": "visualizar", "photo": "visualizar"}

    @property
    def module_code(self):
        status = (self.request.query_params.get("situacao") or "").split(",")[0]
        return STATUS_MODULE.get(status, "provadevida.pendentes")

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("situacao"):
            qs = qs.filter(status__in=p["situacao"].split(","))
        if p.get("campanha"):
            qs = qs.filter(campaign_id=p["campanha"])
        if p.get("vencidas"):
            from django.utils import timezone

            qs = qs.filter(due_date__lt=timezone.localdate())
        term = (p.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(person__name__icontains=term)
            if digits:
                cond |= Q(person__cpf__startswith=digits)
            qs = qs.filter(cond)
        return qs

    @action(detail=True, methods=["post"])
    def register(self, request, pk=None):
        proof = self.get_object()
        _need(request, "provadevida.realizadas:incluir", "registrar prova de vida")
        if proof.status == "BLOQUEADO" or proof.status_before_portal == "BLOQUEADO" and proof.status == "EM_ANALISE":
            _need(request, "provadevida.bloqueados:aprovar", "restabelecer benefícios suspensos")
        try:
            done = date.fromisoformat(request.data.get("done_date") or "")
        except ValueError:
            raise serializers.ValidationError({"done_date": "Data inválida."})
        proof, restored = services.register(proof, request.user, done_date=done, channel=request.data.get("channel", ""),
                                            notes=request.data.get("notes", ""), upload=request.FILES.get("file"),
                                            password=request.data.get("password", ""))
        return Response({**ProofSerializer(proof).data, "restabelecidos": len(restored)})

    @action(detail=True, methods=["post"])
    def waive(self, request, pk=None):
        _need(request, "provadevida.pendentes:editar", "dispensar prova de vida")
        return Response(ProofSerializer(services.waive(self.get_object(), request.user, request.data.get("notes", ""))).data)

    @action(detail=True, methods=["get"])
    def attachment(self, request, pk=None):
        proof = self.get_object()
        if not proof.attachment:
            raise serializers.ValidationError("Sem comprovante anexado.")
        return FileResponse(proof.attachment.open("rb"), as_attachment=True,
                            filename=f"prova-de-vida-{proof.person.cpf}.{proof.attachment.name.rsplit('.', 1)[-1]}")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Recusa a prova enviada pelo Portal (fotos ilegíveis, pessoa diferente...) e avisa o segurado."""
        _need(request, "provadevida.realizadas:incluir", "conferir provas de vida")
        return Response(ProofSerializer(services.portal_reject(self.get_object(), request.user,
                                                               request.data.get("reason", ""))).data)

    @action(detail=True, methods=["get"])
    def photo(self, request, pk=None):
        """Fotos enviadas pelo Portal (?tipo=selfie|documento), só para a equipe conferir."""
        from apps.audit.services import log_event

        proof = self.get_object()
        tipo = request.query_params.get("tipo")
        if tipo == "gesto":
            from django.core.files.storage import default_storage

            try:
                path = proof.portal_frames[int(request.query_params.get("n", 0))]
            except (IndexError, ValueError):
                raise serializers.ValidationError("Foto do gesto não encontrada.")
            f = default_storage.open(path, "rb")
            ext = path.rsplit(".", 1)[-1].lower()
            return FileResponse(f, content_type={"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg"))
        f = proof.portal_selfie if tipo != "documento" else proof.portal_document
        if not f:
            raise serializers.ValidationError("Sem foto enviada.")
        log_event("EXPORT", module="provadevida.realizadas", obj=proof, object_repr=f"Foto da prova de vida — {proof.person.name}")
        ext = f.name.rsplit(".", 1)[-1].lower()
        return FileResponse(f.open("rb"), content_type={"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg"))