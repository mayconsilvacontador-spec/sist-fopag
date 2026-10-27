from rest_framework import serializers

from apps.core.validators import format_cnpj, format_cpf, only_digits

from . import services
from .models import ComprevProcess, MonthlyValue, Movement, ProcessEvent


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class ProcessSerializer(serializers.ModelSerializer):
    direction_display = _display("direction")
    counterpart_kind_display = _display("counterpart_kind")
    benefit_kind_display = _display("benefit_kind")
    status_display = _display("status")
    person_name = serializers.CharField(source="person.name", read_only=True)
    person_cpf = serializers.SerializerMethodField()
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    counterpart_cnpj = serializers.CharField(max_length=18, required=False, allow_blank=True)  # aceita com máscara
    counterpart_cnpj_formatted = serializers.SerializerMethodField()
    benefit_label = serializers.SerializerMethodField()
    averbacao_label = serializers.SerializerMethodField()
    ctc_label = serializers.SerializerMethodField()
    valor_vigente = serializers.SerializerMethodField()
    valor_sugerido = serializers.SerializerMethodField()

    class Meta:
        model = ComprevProcess
        exclude = ["institution", "updated_by"]
        read_only_fields = ["status", "status_date", "comp_start", "backlog_amount", "requirement_text",
                            "requirement_due", "decision_reason", "ended_at", "created_by"]
        extra_kwargs = {"plan": {"required": False}, "counterpart_name": {"required": False},
                        "benefit_kind": {"required": False}}

    def get_person_cpf(self, o):
        return format_cpf(o.person.cpf)

    def get_counterpart_cnpj_formatted(self, o):
        return format_cnpj(o.counterpart_cnpj) if o.counterpart_cnpj else ""

    def get_benefit_label(self, o):
        b = o.benefit
        return f"{b.get_kind_display()} — {b.beneficiary.name} (desde {b.start_date:%d/%m/%Y})" if b else ""

    def get_averbacao_label(self, o):
        a = o.averbacao
        return f"{a.issuer} — {a.start_date:%d/%m/%Y} a {a.end_date:%d/%m/%Y} ({a.certified_days} dias)" if a else ""

    def get_ctc_label(self, o):
        return f"CTC {o.ctc.code} — {o.ctc.destination}" if o.ctc else ""

    def get_valor_vigente(self, o):
        v = services.current_value(o)
        return str(v) if v is not None else None

    def get_valor_sugerido(self, o):
        v = services.suggested_value(o)
        return str(v) if v is not None else None

    def validate_counterpart_cnpj(self, v):
        return only_digits(v)

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and inst.status not in ("CADASTRADO", "ENVIADO", "EXIGENCIA"):
            if set(attrs) - {"notes", "request_number"}:
                raise serializers.ValidationError(
                    "Requerimento já decidido: só é possível alterar o nº do requerimento e as observações.")
        if inst is not None and "direction" in attrs and attrs["direction"] != inst.direction:
            raise serializers.ValidationError({"direction": "O sentido não pode ser alterado."})
        return attrs


class EventSerializer(serializers.ModelSerializer):
    status_from_display = _display("status_from")
    status_to_display = _display("status_to")
    user_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = ProcessEvent
        fields = ["id", "date", "status_from", "status_from_display", "status_to", "status_to_display", "note",
                  "user_name", "created_at"]


class ValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyValue
        fields = ["id", "valid_from", "amount", "reason", "created_at"]


class MovementSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    person_name = serializers.CharField(source="process.person.name", read_only=True)
    request_number = serializers.CharField(source="process.request_number", read_only=True)
    counterpart_name = serializers.CharField(source="process.counterpart_name", read_only=True)
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    difference = serializers.SerializerMethodField()

    class Meta:
        model = Movement
        exclude = ["institution", "updated_by"]

    def get_difference(self, o):
        if o.kind != "MENSAL" or o.expected is None:
            return None
        return str(o.amount - o.expected)
