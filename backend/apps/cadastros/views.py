from rest_framework import mixins, viewsets

from apps.core.views import InstitutionScopedMixin

from . import serializers as s
from .models import Bank, BankBranch, Ente, Organ, Position, Workplace
from .services import ensure_default_banks


class RegistryViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Cadastro de referência: sem exclusão (inativar). ?ativos=1 lista só ativos."""

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("ativos") == "1":
            qs = qs.filter(active=True)
        return qs


class EnteViewSet(RegistryViewSet):
    module_code = "cadastros.entes"
    serializer_class = s.EnteSerializer
    queryset = Ente.objects.all()
    search_fields = ["name", "cnpj"]


class OrganViewSet(RegistryViewSet):
    module_code = "cadastros.orgaos"
    serializer_class = s.OrganSerializer
    queryset = Organ.objects.select_related("ente").all()
    search_fields = ["name", "short_name", "cnpj", "sigfis_code"]
    filterset_fields = ["ente"]


class PositionViewSet(RegistryViewSet):
    module_code = "cadastros.cargos"
    serializer_class = s.PositionSerializer
    queryset = Position.objects.all()
    search_fields = ["name", "career", "cbo"]
    filterset_fields = ["cargo_type"]


class WorkplaceViewSet(RegistryViewSet):
    module_code = "cadastros.lotacao"
    serializer_class = s.WorkplaceSerializer
    queryset = Workplace.objects.select_related("organ").all()
    search_fields = ["name", "code"]
    filterset_fields = ["organ"]


class BankViewSet(RegistryViewSet):
    module_code = "cadastros.bancos"
    serializer_class = s.BankSerializer
    queryset = Bank.objects.all()
    search_fields = ["code", "name"]

    def list(self, request, *args, **kwargs):
        ensure_default_banks(self.get_institution())
        return super().list(request, *args, **kwargs)


class BankBranchViewSet(RegistryViewSet):
    module_code = "cadastros.agencias"
    serializer_class = s.BankBranchSerializer
    queryset = BankBranch.objects.select_related("bank").all()
    search_fields = ["number", "name", "city", "bank__code", "bank__name"]
    filterset_fields = ["bank"]
