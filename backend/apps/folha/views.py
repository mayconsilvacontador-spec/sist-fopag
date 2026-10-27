from datetime import date

from django.db.models import Q
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import has_perm
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import only_digits
from apps.core.views import InstitutionScopedMixin

from . import services
from .models import Consignee, Entry, IrExemption, PayrollEntry, PayrollItem, PayrollRun, Rubric, RunKind
from .serializers import (
    ConsigneeSerializer, EntrySerializer, IrExemptionSerializer, PayrollEntryListSerializer, PayrollEntrySerializer,
    PayrollRunSerializer, RubricSerializer,
)


def _date(value, name):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise serializers.ValidationError({name: "Data inválida."})


def _require(request, perm: str):
    if not has_perm(request, perm):
        raise PermissionDenied("Você não possui permissão para esta operação.")


class CrudNoDelete(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                   mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Sem exclusão: inativar. ?ativos=1 lista só ativos."""

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("ativos") == "1":
            qs = qs.filter(active=True)
        return qs


class RubricViewSet(CrudNoDelete):
    """Rubricas. Alterar rubrica já usada em folha = nova versão (POST {id}/version/ {valid_from, reason, ...})."""

    module_code = "folha.rubricas"
    serializer_class = RubricSerializer
    queryset = Rubric.objects.all()
    search_fields = ["code", "name"]
    filterset_fields = ["kind", "calc", "active"]
    action_permissions = {"version": "editar"}

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("vigentes") == "1":
            qs = qs.filter(valid_to__isnull=True)
        return qs

    def perform_create(self, serializer):
        inst = self.get_institution()
        code = serializer.validated_data["code"]
        if Rubric.objects.filter(institution=inst, code=code).exists():
            raise BusinessRuleError(f"A rubrica {code} já existe. Para alterá-la, crie uma nova versão.")
        r = serializer.save(institution=inst, version=1)
        services.validate_rubric(r)

    def perform_update(self, serializer):
        r = serializer.instance
        if PayrollItem.objects.filter(rubric=r).exists():
            changed = {k for k, v in serializer.validated_data.items() if k != "active" and getattr(r, k) != v}
            if changed:
                raise BusinessRuleError("Rubrica já usada em folha: crie uma nova versão (o histórico é preservado). "
                                        "Só é permitido ativar/inativar.")
        r = serializer.save()
        services.validate_rubric(r)

    @action(detail=True, methods=["post"])
    def version(self, request, pk=None):
        r = self.get_object()
        data = {k: v for k, v in request.data.items() if k not in ("valid_from", "reason")}
        ser = RubricSerializer(r, data=data, partial=True)
        ser.is_valid(raise_exception=True)
        new = services.new_rubric_version(r, ser.validated_data, _date(request.data.get("valid_from"), "valid_from"),
                                          request.data.get("reason", ""))
        return Response(RubricSerializer(new).data, status=201)


class ConsigneeViewSet(CrudNoDelete):
    module_code = "folha.consignacoes"
    serializer_class = ConsigneeSerializer
    queryset = Consignee.objects.all()
    search_fields = ["name", "cnpj"]


class _EntryViewSet(CrudNoDelete):
    """Lançamentos por benefício. Sem exclusão: inativar ou informar competência final."""

    serializer_class = EntrySerializer
    calcs: set[str] = set()
    filterset_fields = ["benefit", "active", "rubric_code", "consignee"]

    def get_queryset(self):
        inst = self.get_institution()
        codes = Rubric.objects.filter(institution=inst, calc__in=self.calcs).values_list("code", flat=True)
        qs = (Entry.objects.filter(institution=inst, rubric_code__in=list(codes))
              .select_related("benefit__beneficiary", "benefit__payroll_group", "consignee", "alimony_beneficiary"))
        term = (self.request.query_params.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(benefit__beneficiary__name__icontains=term) | Q(contract__icontains=term)
            if len(digits) >= 3:
                cond |= Q(benefit__beneficiary__cpf__startswith=digits)
            qs = qs.filter(cond)
        return qs

    def _save(self, serializer, **extra):
        e = Entry(**{**({f.name: getattr(serializer.instance, f.name) for f in Entry._meta.concrete_fields}
                        if serializer.instance else {}), **serializer.validated_data, **extra})
        r = services.validate_entry(e)
        if r.calc not in self.calcs:
            raise BusinessRuleError(f"A rubrica {r.code} não pertence a esta tela.")
        if e.benefit.institution_id != self.get_institution().pk:
            raise BusinessRuleError("Benefício de outra instituição.")
        serializer.save(start=e.start, end=e.end, base=e.base, **extra)

    def perform_create(self, serializer):
        self._save(serializer, institution=self.get_institution())

    def perform_update(self, serializer):
        self._save(serializer)


class AdjustmentViewSet(_EntryViewSet):
    module_code = "folha.diferencas"
    calcs = {"MANUAL"}


class ConsignmentViewSet(_EntryViewSet):
    module_code = "folha.consignacoes"
    calcs = {"CONSIGNACAO"}


class AlimonyViewSet(_EntryViewSet):
    module_code = "folha.pensao_alimenticia"
    calcs = {"PENSAO_ALIMENTICIA"}


class IrExemptionViewSet(CrudNoDelete):
    module_code = "folha.beneficiarios"
    serializer_class = IrExemptionSerializer
    queryset = IrExemption.objects.select_related("person").all()
    filterset_fields = ["person", "active"]


class PayrollRunViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """
    Folhas. POST {year, month, payroll_group, kind} abre. Ações: calculate, check, close, reopen, pay;
    GET entries, comparison, summary, credit.
    """

    module_code = "folha.folha_mensal"
    serializer_class = PayrollRunSerializer
    queryset = PayrollRun.objects.select_related("competence", "payroll_group", "checked_by", "closed_by").all()
    filterset_fields = ["status", "kind", "payroll_group", "competence__year"]
    action_permissions = {a: "visualizar" for a in ("create", "calculate", "check", "close", "reopen", "pay",
                                                     "excluir", "entries", "comparison", "summary", "credit")}

    def get_queryset(self):
        qs = super().get_queryset()
        massa = self.request.query_params.get("massa")
        if massa:
            qs = qs.filter(payroll_group__segment=massa)
        situacoes = [s for s in (self.request.query_params.get("situacoes") or "").split(",") if s]
        if situacoes:
            qs = qs.filter(status__in=situacoes)
        return qs

    def create(self, request, *args, **kwargs):
        from apps.institutions.models import PayrollGroup

        kind = request.data.get("kind") or RunKind.MENSAL
        if kind not in RunKind.values:
            raise serializers.ValidationError({"kind": "Tipo inválido."})
        _require(request, "folha.decimo_terceiro:calcular" if kind == RunKind.DECIMO else "folha.folha_mensal:incluir")
        inst = self.get_institution()
        group = PayrollGroup.objects.filter(institution=inst, pk=request.data.get("payroll_group")).first()
        if group is None:
            raise serializers.ValidationError({"payroll_group": "Escolha a folha (massa)."})
        try:
            year, month = int(request.data.get("year")), int(request.data.get("month"))
        except (TypeError, ValueError):
            raise serializers.ValidationError("Informe ano e mês.")
        run = services.open_run(inst, year=year, month=month, payroll_group=group, kind=kind)
        return Response(PayrollRunSerializer(run).data, status=201)

    def _ok(self, run):
        return Response(PayrollRunSerializer(self.get_queryset().get(pk=run.pk)).data)

    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        run = self.get_object()
        _require(request, "folha.decimo_terceiro:calcular" if run.kind == RunKind.DECIMO else "folha.calculo:calcular")
        return self._ok(services.calculate(run))

    @action(detail=True, methods=["post"])
    def check(self, request, pk=None):
        _require(request, "folha.conferencia:aprovar")
        return self._ok(services.check(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        _require(request, "folha.fechamento:fechar")
        return self._ok(services.close(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        _require(request, "folha.reabertura:reabrir")
        return self._ok(services.reopen(self.get_object(), request.data.get("justification", "")))

    @action(detail=True, methods=["post"])
    def excluir(self, request, pk=None):
        _require(request, "folha.folha_mensal:excluir")
        services.delete_run(self.get_object(), request.user, request.data.get("justification", ""),
                            request.data.get("password", ""))
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        _require(request, "folha.fechamento:fechar")
        return self._ok(services.mark_paid(self.get_object(), _date(request.data.get("payment_date"), "payment_date")))

    @action(detail=True, methods=["get"])
    def entries(self, request, pk=None):
        run = self.get_object()
        qs = run.entries.select_related("beneficiary", "benefit", "run__competence", "run__payroll_group")
        term = (request.query_params.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(beneficiary__name__icontains=term)
            if len(digits) >= 3:
                cond |= Q(beneficiary__cpf__startswith=digits)
            qs = qs.filter(cond)
        if request.query_params.get("avisos") == "1":
            qs = qs.exclude(warnings=[])
        page = self.paginate_queryset(qs.order_by("beneficiary__name"))
        return self.get_paginated_response(PayrollEntryListSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def comparison(self, request, pk=None):
        _require(request, "folha.conferencia:visualizar")
        return Response(services.comparison(self.get_object()))

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        _require(request, "folha.relatorios:visualizar")
        return Response(services.rubric_summary(self.get_object()))

    @action(detail=True, methods=["get"])
    def credit(self, request, pk=None):
        if not (has_perm(request, "folha.arquivo_bancario:exportar") or has_perm(request, "folha.relatorios:exportar")):
            raise PermissionDenied("Você não possui permissão para exportar a relação de crédito.")
        return Response(services.credit_list(self.get_object()))


class PayslipViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Contracheques (folhas calculadas). ?beneficiary=&run="""

    module_code = "folha.contracheques"
    queryset = PayrollEntry.objects.select_related(
        "beneficiary", "benefit__instituidor", "run__competence", "run__payroll_group").prefetch_related("items")
    filterset_fields = ["beneficiary", "run", "benefit"]

    def get_serializer_class(self):
        return PayrollEntryListSerializer if self.action == "list" else PayrollEntrySerializer

    def get_queryset(self):
        return super().get_queryset().order_by("-run__competence__year", "-run__competence__month", "run__kind")


class RetroactiveViewSet(InstitutionScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Retroativos pagos/calculados (primeira folha de benefícios concedidos no SIST), com memória por mês."""

    module_code = "folha.retroativos"
    queryset = PayrollEntry.objects.select_related("beneficiary", "run__competence", "run__payroll_group")

    def get_queryset(self):
        return (super().get_queryset().filter(items__rubric__calc="RETROATIVO").distinct()
                .order_by("-run__competence__year", "-run__competence__month", "beneficiary__name"))

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        rows = []
        for e in page:
            items = [i for i in e.items.all() if i.rubric.calc in ("RETROATIVO", "IRRF_RRA")]
            rows.append({"id": str(e.pk), "run": str(e.run_id), "competencia": str(e.run.competence),
                         "folha": e.run.payroll_group.code, "status": e.run.get_status_display(),
                         "beneficiario": e.beneficiary.name,
                         "valor": str(sum((i.amount for i in items if i.rubric.calc == "RETROATIVO"), 0)),
                         "irrf_rra": str(sum((i.amount for i in items if i.rubric.calc == "IRRF_RRA"), 0)),
                         "meses": (e.memory or {}).get("retroativo", [])})
        return self.get_paginated_response(rows)


class IncomeReportView(InstitutionScopedMixin, APIView):
    """GET ?person=<id>&year=AAAA — informe de rendimentos (folhas fechadas/pagas)."""

    module_code = "folha.informe_rendimentos"

    def get(self, request):
        from apps.people.models import Person

        inst = self.get_institution()
        person = Person.objects.filter(institution=inst, pk=request.query_params.get("person")).first()
        if person is None:
            raise serializers.ValidationError({"person": "Escolha o beneficiário."})
        try:
            year = int(request.query_params.get("year"))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"year": "Ano inválido."})
        return Response(services.income_report(inst, person, year))
