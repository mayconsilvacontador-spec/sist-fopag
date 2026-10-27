from rest_framework import serializers

from apps.cadastros.serializers import ScopedSerializer
from apps.core.validators import format_cpf

from .models import Consignee, Entry, IrExemption, PayrollEntry, PayrollItem, PayrollRun, Rubric


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class RubricSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    calc_display = _display("calc")

    class Meta:
        model = Rubric
        exclude = ["institution", "updated_by"]
        read_only_fields = ["version", "valid_to", "change_reason"]


class ConsigneeSerializer(ScopedSerializer):
    kind_display = _display("kind")

    class Meta:
        model = Consignee
        exclude = ["institution", "updated_by"]


class EntrySerializer(ScopedSerializer):
    scoped_fks = ("benefit", "consignee", "alimony_beneficiary")
    beneficiary_name = serializers.CharField(source="benefit.beneficiary.name", read_only=True)
    beneficiary_cpf = serializers.SerializerMethodField()
    folha = serializers.CharField(source="benefit.payroll_group.code", read_only=True)
    consignee_name = serializers.CharField(source="consignee.name", read_only=True, default="")
    alimony_beneficiary_name = serializers.CharField(source="alimony_beneficiary.name", read_only=True, default="")
    rubric_name = serializers.SerializerMethodField()

    class Meta:
        model = Entry
        exclude = ["institution", "updated_by"]
        read_only_fields = ["paid_installments"]

    def get_beneficiary_cpf(self, obj):
        return format_cpf(obj.benefit.beneficiary.cpf)

    def get_rubric_name(self, obj):
        r = Rubric.objects.filter(institution=obj.institution_id, code=obj.rubric_code).order_by("-version").first()
        return r.name if r else ""


class IrExemptionSerializer(ScopedSerializer):
    scoped_fks = ("person",)
    person_name = serializers.CharField(source="person.name", read_only=True)

    class Meta:
        model = IrExemption
        exclude = ["institution", "updated_by"]


class PayrollRunSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    status_display = _display("status")
    competence_label = serializers.CharField(source="competence.__str__", read_only=True)
    year = serializers.IntegerField(source="competence.year", read_only=True)
    month = serializers.IntegerField(source="competence.month", read_only=True)
    folha = serializers.CharField(source="payroll_group.code", read_only=True)
    folha_name = serializers.CharField(source="payroll_group.name", read_only=True)
    segment = serializers.CharField(source="payroll_group.segment", read_only=True)
    checked_by_name = serializers.CharField(source="checked_by.full_name", read_only=True, default="")
    closed_by_name = serializers.CharField(source="closed_by.full_name", read_only=True, default="")

    class Meta:
        model = PayrollRun
        exclude = ["institution", "updated_by", "close_effects"]


class PayrollItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollItem
        fields = ["id", "code", "name", "kind", "reference", "amount"]


class PayrollEntryListSerializer(serializers.ModelSerializer):
    beneficiary_name = serializers.CharField(source="beneficiary.name", read_only=True)
    beneficiary_cpf = serializers.SerializerMethodField()
    kind = serializers.CharField(source="benefit.kind", read_only=True)
    registration = serializers.CharField(source="benefit.registration", read_only=True)
    competencia = serializers.CharField(source="run.competence.__str__", read_only=True)
    run_kind = serializers.CharField(source="run.get_kind_display", read_only=True)
    folha = serializers.CharField(source="run.payroll_group.code", read_only=True)

    class Meta:
        model = PayrollEntry
        fields = ["id", "benefit", "beneficiary", "beneficiary_name", "beneficiary_cpf", "kind", "registration",
                  "competencia", "run_kind", "folha", "gross", "discounts", "net", "warnings"]

    def get_beneficiary_cpf(self, obj):
        return format_cpf(obj.beneficiary.cpf)


class PayrollEntrySerializer(PayrollEntryListSerializer):
    items = PayrollItemSerializer(many=True, read_only=True)
    run = PayrollRunSerializer(read_only=True)
    kind_display = serializers.CharField(source="benefit.get_kind_display", read_only=True)
    instituidor_name = serializers.CharField(source="benefit.instituidor.name", read_only=True, default="")
    start_date = serializers.DateField(source="benefit.start_date", read_only=True)

    class Meta(PayrollEntryListSerializer.Meta):
        fields = PayrollEntryListSerializer.Meta.fields + [
            "items", "run", "kind_display", "instituidor_name", "start_date", "ir_base", "rpps_base", "bank", "memory"]
