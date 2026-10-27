from rest_framework import serializers

from apps.cadastros.serializers import ScopedSerializer

from . import services
from .models import (
    AccountingExport, AccountingMapping, Aporte, BankFile, Contribution, Installment, InstallmentAgreement,
    PaymentBatch, PaymentItem, Revenue, StatementLine, TreasuryAccount,
)


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class TreasuryAccountSerializer(ScopedSerializer):
    scoped_fks = ("plan", "bank")
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    bank_label = serializers.CharField(source="bank.__str__", read_only=True)
    purpose_display = _display("purpose")
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = TreasuryAccount
        exclude = ["institution", "updated_by"]


class PaymentItemSerializer(serializers.ModelSerializer):
    beneficiary_name = serializers.CharField(source="beneficiary.name", read_only=True)
    status_display = _display("status")

    class Meta:
        model = PaymentItem
        fields = ["id", "beneficiary", "beneficiary_name", "our_number", "bank", "amount", "status", "status_display",
                  "return_code", "return_message"]


class PaymentBatchSerializer(serializers.ModelSerializer):
    status_display = _display("status")
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    account_label = serializers.CharField(source="account.__str__", read_only=True)
    run_label = serializers.CharField(source="payroll_run.__str__", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.full_name", read_only=True, default="")
    counts = serializers.SerializerMethodField()

    class Meta:
        model = PaymentBatch
        exclude = ["institution", "updated_by"]

    def get_counts(self, obj):
        from django.db.models import Count

        return {r["status"]: r["n"] for r in obj.items.values("status").annotate(n=Count("id"))}


class BankFileSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    account_label = serializers.CharField(source="account.__str__", read_only=True)
    batch_number = serializers.IntegerField(source="batch.number", read_only=True, default=None)
    user_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = BankFile
        exclude = ["institution", "updated_by", "content"]


class _Due(ScopedSerializer):
    paid = serializers.SerializerMethodField()
    situation = serializers.SerializerMethodField()
    plan_code = serializers.CharField(source="plan.code", read_only=True)

    def get_paid(self, obj):
        return str(services.paid_of(obj))

    def get_situation(self, obj):
        return services.status_of(obj.amount, services.paid_of(obj), obj.due_date)


class ContributionSerializer(_Due):
    scoped_fks = ("plan", "organ")
    kind_display = _display("kind")
    source_display = _display("source")
    organ_name = serializers.CharField(source="organ.name", read_only=True, default="Folha de benefícios")

    class Meta:
        model = Contribution
        exclude = ["institution", "updated_by"]
        read_only_fields = ["payroll_run", "amount"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("competence"):
            attrs["competence"] = attrs["competence"].replace(day=1)
        base = attrs.get("base", getattr(self.instance, "base", None))
        rate = attrs.get("rate", getattr(self.instance, "rate", None))
        if base is not None and rate is not None:
            attrs["amount"] = services.q(base * rate)
        if attrs.get("source", getattr(self.instance, "source", "")) == "FOLHA" and self.instance:
            raise serializers.ValidationError("Contribuição gerada pela folha não é editada.")
        return attrs


class AporteSerializer(_Due):
    scoped_fks = ("plan", "life_purchase")
    kind_display = _display("kind")

    class Meta:
        model = Aporte
        exclude = ["institution", "updated_by"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("competence"):
            attrs["competence"] = attrs["competence"].replace(day=1)
        return attrs


class InstallmentSerializer(_Due):
    class Meta:
        model = Installment
        fields = ["id", "number", "due_date", "amount", "paid", "situation", "plan_code"]

    plan_code = serializers.CharField(source="agreement.plan.code", read_only=True)


class AgreementSerializer(ScopedSerializer):
    scoped_fks = ("plan", "organ")
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    organ_name = serializers.CharField(source="organ.name", read_only=True)
    status_display = _display("status")
    index_display = _display("index")
    progress = serializers.SerializerMethodField()

    class Meta:
        model = InstallmentAgreement
        exclude = ["institution", "updated_by"]

    def get_progress(self, obj):
        from django.utils import timezone

        today = timezone.localdate()
        parcels = list(obj.parcels.all())
        paid = sum(1 for p in parcels if services.paid_of(p) >= p.amount)
        late = sum(1 for p in parcels if p.due_date < today and services.paid_of(p) < p.amount)
        return {"pagas": paid, "em_atraso": late, "total": len(parcels)}


class RevenueSerializer(ScopedSerializer):
    scoped_fks = ("plan", "account")
    kind_display = _display("kind")
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    account_label = serializers.CharField(source="account.__str__", read_only=True, default="")

    class Meta:
        model = Revenue
        exclude = ["institution", "updated_by"]
        read_only_fields = ["contribution", "aporte", "installment", "active"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("kind") in ("CONTRIBUICAO", "APORTE", "PARCELAMENTO"):
            raise serializers.ValidationError("Contribuições, aportes e parcelas são baixados na própria tela (Registrar pagamento).")
        acc, plan = attrs.get("account"), attrs.get("plan")
        if acc and plan and acc.plan_id != plan.pk:
            raise serializers.ValidationError({"account": "Segregação de massas: a conta é de outro plano."})
        if attrs.get("competence"):
            attrs["competence"] = attrs["competence"].replace(day=1)
        return attrs


class StatementLineSerializer(serializers.ModelSerializer):
    revenue_label = serializers.CharField(source="revenue.description", read_only=True, default="")
    batch_number = serializers.IntegerField(source="batch.number", read_only=True, default=None)

    class Meta:
        model = StatementLine
        exclude = ["institution", "updated_by"]


class MappingSerializer(ScopedSerializer):
    scoped_fks = ("plan",)
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    source_display = _display("source")

    class Meta:
        model = AccountingMapping
        exclude = ["institution", "updated_by"]


class AccountingExportSerializer(serializers.ModelSerializer):
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    user_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = AccountingExport
        exclude = ["institution", "updated_by", "content"]
