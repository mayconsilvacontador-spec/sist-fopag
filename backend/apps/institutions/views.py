from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.views import InstitutionScopedMixin, get_justification

from . import services
from .models import BenefitPlan, Competence, FiscalYear, LifePurchase, Parameter, PayrollGroup
from .serializers import (
    BenefitPlanSerializer, CompetenceSerializer, FiscalYearSerializer, InstitutionSerializer,
    LifePurchaseSerializer, ParameterSerializer, PayrollGroupSerializer,
)


class CurrentInstitutionView(APIView):
    """Dados cadastrais da instituição corrente."""

    module_code = "admin.instituicao"

    def get(self, request):
        return Response(InstitutionSerializer(request.institution).data)

    def patch(self, request):
        ser = InstitutionSerializer(request.institution, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class LifePurchaseToggleView(APIView):
    """POST {enabled: bool, justification: str} — liga/desliga a Compra de Vidas."""

    module_code = "admin.instituicao"
    action_permissions = {"POST": "editar"}

    def post(self, request):
        enabled = request.data.get("enabled")
        if not isinstance(enabled, bool):
            return Response({"enabled": ["Informe verdadeiro ou falso."]}, status=400)
        inst = services.set_life_purchase(request.institution, enabled, get_justification(request))
        return Response(InstitutionSerializer(inst).data)


class PayrollGroupViewSet(InstitutionScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Folhas (uma por massa). Lista usada pelo filtro global; criadas pelo sistema."""

    serializer_class = PayrollGroupSerializer
    queryset = PayrollGroup.objects.select_related("plan").all()
    pagination_class = None

    def list(self, request, *args, **kwargs):
        services.ensure_payroll_groups(self.get_institution())
        return super().list(request, *args, **kwargs)


class LifePurchaseViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Lotes de Compra de Vidas. Não há exclusão: inativar."""

    module_code = "admin.instituicao"
    serializer_class = LifePurchaseSerializer
    queryset = LifePurchase.objects.select_related("origin_plan", "destination_plan").all()

    def perform_create(self, serializer):
        institution = self.get_institution()
        serializer.save(institution=institution, number=services.next_life_purchase_number(institution))


class BenefitPlanViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Planos (segregação de massas). Não há exclusão: inativar."""

    module_code = "admin.instituicao"
    serializer_class = BenefitPlanSerializer
    queryset = BenefitPlan.objects.all()
    filterset_fields = ["kind", "active"]

    def get_permissions(self):
        # A lista de planos é usada no filtro global de todas as telas
        if self.action == "list":
            self.module_code = None
        return super().get_permissions()


class FiscalYearViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.CreateModelMixin, viewsets.GenericViewSet):
    module_code = "admin.exercicios"
    serializer_class = FiscalYearSerializer
    queryset = FiscalYear.objects.select_related("closed_by").all()
    action_permissions = {"close": "fechar", "reopen": "reabrir"}

    def get_permissions(self):
        # A lista de exercícios alimenta o seletor da barra superior
        if self.action == "list":
            self.module_code = None
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        fy = services.close_fiscal_year(self.get_object(), request.user)
        return Response(self.get_serializer(fy).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        fy = services.reopen_fiscal_year(self.get_object(), get_justification(request))
        return Response(self.get_serializer(fy).data)


class CompetenceViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.CreateModelMixin, viewsets.GenericViewSet):
    module_code = "admin.competencias"
    serializer_class = CompetenceSerializer
    queryset = Competence.objects.select_related("closed_by").all()
    filterset_fields = ["year", "status"]
    action_permissions = {"close": "fechar", "reopen": "reabrir", "set_reference": "editar"}

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        comp = services.create_competence(
            self.get_institution(), ser.validated_data["year"], ser.validated_data["month"]
        )
        return Response(self.get_serializer(comp).data, status=201)

    @action(detail=True, methods=["post"], url_path="set-reference")
    def set_reference(self, request, pk=None):
        comp = services.set_reference_competence(self.get_object())
        return Response(self.get_serializer(comp).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        comp = services.close_competence(self.get_object(), request.user)
        return Response(self.get_serializer(comp).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        comp = services.reopen_competence(self.get_object(), get_justification(request))
        return Response(self.get_serializer(comp).data)


class ParameterViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                       mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    Parâmetros versionados. POST cria nova versão (encerrando a anterior).
    Não existe alteração nem exclusão.
    """

    module_code = "admin.parametros"
    serializer_class = ParameterSerializer
    queryset = Parameter.objects.select_related("created_by").all()
    search_fields = ["key", "description"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("vigentes") == "1":
            today = timezone.localdate()
            qs = qs.filter(valid_from__lte=today).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        key = self.request.query_params.get("key")
        if key:
            qs = qs.filter(key=key)
        return qs.order_by("key", "-version")

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        param = services.set_parameter(
            self.get_institution(), d["key"], d["value"], d["valid_from"],
            description=d.get("description", ""), change_reason=d.get("change_reason", ""),
        )
        return Response(self.get_serializer(param).data, status=201)
