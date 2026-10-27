from datetime import date

from django.http import HttpResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import has_perm
from apps.core.exceptions import BusinessRuleError
from apps.core.views import InstitutionScopedMixin, get_justification

from . import services
from .models import (
    AccountingExport, AccountingMapping, Aporte, BankFile, Contribution, Installment, InstallmentAgreement,
    PaymentBatch, Revenue, StatementLine, TreasuryAccount,
)
from .serializers import (
    AccountingExportSerializer, AgreementSerializer, AporteSerializer, BankFileSerializer, ContributionSerializer,
    InstallmentSerializer, MappingSerializer, PaymentBatchSerializer, PaymentItemSerializer, RevenueSerializer,
    StatementLineSerializer, TreasuryAccountSerializer,
)


def _date(value, name):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        raise serializers.ValidationError({name: "Data inválida."})


def _competence(value):
    s = str(value or "")
    try:
        return date(int(s[:4]), int(s[5:7]), 1)
    except (TypeError, ValueError):
        raise serializers.ValidationError({"competence": "Competência inválida (AAAA-MM)."})


def _require(request, perm):
    if not has_perm(request, perm):
        raise PermissionDenied("Você não possui permissão para esta operação.")


def _text_file(content: str, name: str, ctype="text/plain"):
    resp = HttpResponse(content.encode("latin-1", errors="replace") if ctype == "text/plain" else content,
                        content_type=f"{ctype}; charset={'iso-8859-1' if ctype == 'text/plain' else 'utf-8'}")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


def _upload(request) -> tuple[str, str]:
    f = request.FILES.get("file")
    if f is None:
        raise serializers.ValidationError({"file": "Envie o arquivo."})
    if f.size > 20 * 1024 * 1024:
        raise serializers.ValidationError({"file": "Arquivo muito grande (máx. 20 MB)."})
    raw = f.read()
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc), f.name
        except UnicodeDecodeError:
            continue
    raise serializers.ValidationError({"file": "Codificação do arquivo não reconhecida."})


class CrudNoDelete(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                   mixins.UpdateModelMixin, viewsets.GenericViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("ativos") == "1" and hasattr(qs.model, "active"):
            qs = qs.filter(active=True)
        return qs

    def _account(self, pk):
        acc = TreasuryAccount.objects.filter(institution=self.get_institution(), pk=pk).first() if pk else None
        if pk and acc is None:
            raise serializers.ValidationError({"account": "Conta não encontrada."})
        return acc

    def _pay(self, target, request):
        from apps.concessao.services import _money

        d = request.data
        amount = _money(d.get("amount"))
        if amount is None:
            raise serializers.ValidationError({"amount": "Valor inválido (ex.: 1.234,56)."})
        rev = services.register_payment(
            target, amount=amount, when=_date(d.get("date"), "date"), fines=_money(d.get("fines") or "0") or 0,
            account=self._account(d.get("account")), document=d.get("document", ""))
        return Response(RevenueSerializer(rev).data, status=201)


# ------------------------------------------------------------------ financeiro
class TreasuryAccountViewSet(CrudNoDelete):
    module_code = "financeiro.bancos"
    serializer_class = TreasuryAccountSerializer
    queryset = TreasuryAccount.objects.select_related("plan", "bank").all()
    filterset_fields = ["plan", "purpose", "active"]


class PaymentBatchViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """POST {run, account, payment_date} cria lote; approve, cancel {justification}, remittance, confirm."""

    module_code = "financeiro.pagamentos"
    serializer_class = PaymentBatchSerializer
    queryset = PaymentBatch.objects.select_related("plan", "account__bank", "account__plan", "payroll_run__competence",
                                                   "payroll_run__payroll_group", "approved_by").all()
    filterset_fields = ["status", "plan", "payroll_run"]
    action_permissions = {"create": "incluir", "approve": "aprovar", "cancel": "editar", "remittance": "visualizar",
                          "confirm": "aprovar", "items": "visualizar"}

    def create(self, request, *args, **kwargs):
        from apps.folha.models import PayrollRun

        inst = self.get_institution()
        run = PayrollRun.objects.filter(institution=inst, pk=request.data.get("run")).first()
        acc = TreasuryAccount.objects.filter(institution=inst, pk=request.data.get("account")).first()
        if run is None or acc is None:
            raise serializers.ValidationError("Escolha a folha e a conta pagadora.")
        batch = services.create_batch(run, acc, _date(request.data.get("payment_date"), "payment_date"))
        return Response(PaymentBatchSerializer(batch).data, status=201)

    @action(detail=True, methods=["get"])
    def items(self, request, pk=None):
        page = self.paginate_queryset(self.get_object().items.select_related("beneficiary"))
        return self.get_paginated_response(PaymentItemSerializer(page, many=True).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(PaymentBatchSerializer(services.approve_batch(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(PaymentBatchSerializer(services.cancel_batch(self.get_object(), get_justification(request))).data)

    @action(detail=True, methods=["post"])
    def remittance(self, request, pk=None):
        _require(request, "financeiro.arquivos_bancarios:incluir")
        f = services.generate_remittance(self.get_object())
        return Response(BankFileSerializer(f).data, status=201)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return Response(PaymentBatchSerializer(
            services.mark_items_paid_manually(self.get_object(), get_justification(request))).data)


class BankFileViewSet(InstitutionScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Arquivos bancários. GET {id}/download/. POST import-return {account, file} (retorno CNAB 240)."""

    module_code = "financeiro.arquivos_bancarios"
    serializer_class = BankFileSerializer
    queryset = BankFile.objects.select_related("account__bank", "account__plan", "batch", "created_by").all()
    filterset_fields = ["kind", "account", "batch"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {"download": "exportar", "import_return": "incluir"}

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        f = self.get_queryset().get(pk=pk)
        return _text_file(f.content, f.file_name)

    @action(detail=False, methods=["post"], url_path="import-return")
    def import_return(self, request):
        content, name = _upload(request)
        acc = TreasuryAccount.objects.filter(institution=self.get_institution(), pk=request.data.get("account")).first()
        if acc is None:
            raise serializers.ValidationError({"account": "Escolha a conta."})
        return Response(services.import_return(self.get_institution(), acc, content, name))


class StatementViewSet(InstitutionScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Conciliação bancária: import {account, file OFX}; auto {account}; {id}/match {revenue|batch|note}."""

    module_code = "financeiro.conciliacao"
    serializer_class = StatementLineSerializer
    queryset = StatementLine.objects.select_related("revenue", "batch").all()
    filterset_fields = ["account", "reconciled"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {"import_statement": "editar", "auto": "editar", "match": "aprovar"}

    @action(detail=False, methods=["post"], url_path="import")
    def import_statement(self, request):
        content, name = _upload(request)
        acc = TreasuryAccount.objects.filter(institution=self.get_institution(), pk=request.data.get("account")).first()
        if acc is None:
            raise serializers.ValidationError({"account": "Escolha a conta."})
        return Response(services.import_statement(self.get_institution(), acc, content, name))

    @action(detail=False, methods=["post"])
    def auto(self, request):
        acc = TreasuryAccount.objects.filter(institution=self.get_institution(), pk=request.data.get("account")).first()
        if acc is None:
            raise serializers.ValidationError({"account": "Escolha a conta."})
        return Response({"conciliados": services.auto_match(acc)})

    @action(detail=True, methods=["post"])
    def match(self, request, pk=None):
        line = self.get_queryset().get(pk=pk)
        inst = self.get_institution()
        rev = Revenue.objects.filter(institution=inst, pk=request.data.get("revenue")).first() \
            if request.data.get("revenue") else None
        bat = PaymentBatch.objects.filter(institution=inst, pk=request.data.get("batch")).first() \
            if request.data.get("batch") else None
        return Response(StatementLineSerializer(services.reconcile_manually(line, revenue=rev, batch=bat,
                                                                            note=request.data.get("note", ""))).data)


class MappingViewSet(CrudNoDelete):
    module_code = "financeiro.integracao_contabil"
    serializer_class = MappingSerializer
    queryset = AccountingMapping.objects.select_related("plan").all()
    filterset_fields = ["plan", "source", "active"]
    action_permissions = {"preview": "visualizar", "export": "exportar", "exports": "visualizar",
                          "download": "exportar"}

    def _plan(self, request):
        from apps.institutions.models import BenefitPlan

        src = request.query_params if request.method == "GET" else request.data
        plan = BenefitPlan.objects.filter(institution=self.get_institution(), pk=src.get("plan")).first()
        if plan is None:
            raise serializers.ValidationError({"plan": "Escolha o plano."})
        return plan, _competence(src.get("competence"))

    @action(detail=False, methods=["get"])
    def preview(self, request):
        plan, comp = self._plan(request)
        lines, unmapped = services.accounting_lines(self.get_institution(), plan, comp)
        return Response({"lancamentos": [{**ln, "valor": str(ln["valor"])} for ln in lines], "sem_de_para": unmapped})

    @action(detail=False, methods=["post"])
    def export(self, request):
        plan, comp = self._plan(request)
        return Response(AccountingExportSerializer(services.export_accounting(self.get_institution(), plan, comp)).data,
                        status=201)

    @action(detail=False, methods=["get"])
    def exports(self, request):
        qs = AccountingExport.objects.filter(institution=self.get_institution()).select_related("plan", "created_by")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(AccountingExportSerializer(page, many=True).data)

    @action(detail=False, methods=["get"], url_path=r"exports/(?P<export_id>[^/.]+)/download")
    def download(self, request, export_id=None):
        exp = AccountingExport.objects.get(institution=self.get_institution(), pk=export_id)
        return _text_file("﻿" + exp.content, f"contabil-{exp.plan.code}-{exp.period:%Y-%m}.csv", "text/csv")


# ------------------------------------------------------------------ arrecadação
class ContributionViewSet(CrudNoDelete):
    """Contribuições. ?kind=SERVIDOR|PATRONAL|APOSENTADOS. estimate {competence}; from-payroll {run}; {id}/pay."""

    serializer_class = ContributionSerializer
    queryset = Contribution.objects.select_related("plan", "organ").all()
    filterset_fields = ["kind", "plan", "organ", "competence", "source"]
    action_permissions = {"estimate": "incluir", "from_payroll": "incluir", "pay": "editar"}

    @property
    def module_code(self):
        kind = self.request.query_params.get("kind") or (self.request.data.get("kind")
                                                         if hasattr(self.request, "data") else None)
        return "arrecadacao.patronal" if kind == "PATRONAL" else "arrecadacao.servidor"

    @action(detail=False, methods=["post"])
    def estimate(self, request):
        return Response(services.estimate_contributions(self.get_institution(), _competence(request.data.get("competence"))))

    @action(detail=False, methods=["post"], url_path="from-payroll")
    def from_payroll(self, request):
        from apps.folha.models import PayrollRun

        run = PayrollRun.objects.filter(institution=self.get_institution(), pk=request.data.get("run")).first()
        if run is None:
            raise serializers.ValidationError({"run": "Escolha a folha."})
        return Response(ContributionSerializer(services.contributions_from_payroll(run)).data, status=201)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        return self._pay(self.get_object(), request)


class AporteViewSet(CrudNoDelete):
    module_code = "arrecadacao.aportes"
    serializer_class = AporteSerializer
    queryset = Aporte.objects.select_related("plan").all()
    filterset_fields = ["kind", "plan"]
    action_permissions = {"pay": "editar", "insufficiency": "visualizar"}

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        return self._pay(self.get_object(), request)

    @action(detail=False, methods=["get"])
    def insufficiency(self, request):
        return Response(services.insufficiency(self.get_institution(), _competence(request.query_params.get("competence"))))


class AgreementViewSet(CrudNoDelete):
    module_code = "arrecadacao.parcelamentos"
    serializer_class = AgreementSerializer
    queryset = InstallmentAgreement.objects.select_related("plan", "organ").prefetch_related("parcels").all()
    filterset_fields = ["plan", "organ", "status"]
    action_permissions = {"parcels": "visualizar", "pay_parcel": "editar"}

    def perform_create(self, serializer):
        ag = serializer.save(institution=self.get_institution())
        services.regenerate_installments(ag)

    def perform_update(self, serializer):
        ag = serializer.save()
        if {"principal", "installments", "first_due"} & set(serializer.validated_data):
            services.regenerate_installments(ag)

    @action(detail=True, methods=["get"])
    def parcels(self, request, pk=None):
        return Response(InstallmentSerializer(self.get_object().parcels.all(), many=True).data)

    @action(detail=True, methods=["post"], url_path=r"parcels/(?P<parcel_id>[^/.]+)/pay")
    def pay_parcel(self, request, pk=None, parcel_id=None):
        parcel = Installment.objects.filter(agreement=self.get_object(), pk=parcel_id).first()
        if parcel is None:
            raise serializers.ValidationError("Parcela não encontrada.")
        return self._pay(parcel, request)


class RevenueViewSet(CrudNoDelete):
    """Receitas. Inclusão direta só para COMPREV, rendimentos e outras; estorno = {id}/reverse."""

    module_code = "arrecadacao.receitas"
    serializer_class = RevenueSerializer
    queryset = Revenue.objects.select_related("plan", "account__bank").all()
    filterset_fields = ["kind", "plan", "competence", "active"]
    action_permissions = {"reverse": "editar"}

    def perform_update(self, serializer):
        raise serializers.ValidationError("Receitas não são alteradas: estorne e lance novamente.")

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        return Response(RevenueSerializer(services.reverse_revenue(self.get_object(), get_justification(request))).data)


class ReconciliationView(InstitutionScopedMixin, APIView):
    """GET ?competence=AAAA-MM&plan= — devido × pago."""

    module_code = "arrecadacao.conciliacao"

    def get(self, request):
        return Response(services.reconciliation(self.get_institution(), _competence(request.query_params.get("competence")),
                                                request.query_params.get("plan") or None))


class DivergencesView(InstitutionScopedMixin, APIView):
    module_code = "arrecadacao.divergencias"

    def get(self, request):
        return Response(services.divergences(self.get_institution()))


class RatesView(InstitutionScopedMixin, APIView):
    """GET alíquotas com vigências (?competencia=MM/AAAA devolve as vigentes no mês); POST nova vigência
    {tipo: SERVIDOR|PATRONAL, percentual, inicio (AAAA-MM-DD ou MM/AAAA), fundamento, motivo}."""

    module_code = "arrecadacao.aliquotas"

    def get(self, request):
        from . import aliquotas

        comp = request.query_params.get("competencia")
        if comp:
            from apps.pessoal.ficha import _comp

            try:
                on = _comp(comp)
            except ValueError as exc:
                raise BusinessRuleError(str(exc))
            return Response(aliquotas.rates_on(self.get_institution(), on))
        return Response(aliquotas.listing(self.get_institution()))

    def post(self, request):
        from apps.pessoal.ficha import _comp

        from . import aliquotas

        try:
            start = _comp(request.data.get("inicio"))
        except ValueError:
            raise BusinessRuleError("Informe o início da vigência (mês/ano).")
        aliquotas.add_version(self.get_institution(), str(request.data.get("tipo") or ""), request.data.get("percentual"),
                              start, str(request.data.get("fundamento") or ""), str(request.data.get("motivo") or ""))
        return Response(aliquotas.listing(self.get_institution()), status=201)
