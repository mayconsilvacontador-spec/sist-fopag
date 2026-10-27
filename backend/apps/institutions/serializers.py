from rest_framework import serializers

from apps.core.validators import format_cnpj, is_valid_cnpj, only_digits

from .models import (
    BenefitPlan, Competence, FiscalYear, Institution, LifePurchase, Parameter, PayrollGroup,
)


class InstitutionSerializer(serializers.ModelSerializer):
    # Aceitam valores com máscara; os validadores normalizam para dígitos
    cnpj = serializers.CharField(max_length=18, required=False, allow_blank=True, allow_null=True)
    ente_cnpj = serializers.CharField(max_length=18, required=False, allow_blank=True)
    cep = serializers.CharField(max_length=9, required=False, allow_blank=True)
    cnpj_formatado = serializers.SerializerMethodField()

    class Meta:
        model = Institution
        fields = [
            "id", "kind", "name", "short_name", "cnpj", "cnpj_formatado", "ente_name", "ente_cnpj",
            "address", "district", "city", "uf", "cep", "phone", "email", "website", "ibge_code",
            "life_purchase_enabled", "active", "created_at", "updated_at",
            "has_coat_of_arms", "has_background", "background_intensity",
        ]
        read_only_fields = ["life_purchase_enabled", "active", "created_at", "updated_at"]

    has_coat_of_arms = serializers.SerializerMethodField()
    has_background = serializers.SerializerMethodField()

    def get_has_coat_of_arms(self, obj):
        return bool(obj.coat_of_arms)

    def get_has_background(self, obj):
        return bool(obj.background_image)

    def validate_background_intensity(self, v):
        if not 5 <= v <= 60:
            raise serializers.ValidationError("Informe entre 5% e 60%.")
        return v

    def validate_kind(self, value):
        if self.instance and value != "RPPS" and self.instance.life_purchase_enabled:
            raise serializers.ValidationError("Desative a Compra de Vidas antes de mudar o tipo de órgão.")
        return value

    def validate_ibge_code(self, value):
        digits = only_digits(value)
        if digits and len(digits) != 7:
            raise serializers.ValidationError("O código IBGE deve conter 7 dígitos.")
        return digits

    def get_cnpj_formatado(self, obj):
        return format_cnpj(obj.cnpj) if obj.cnpj else ""

    def _clean_cnpj(self, value, field):
        if not value:
            return None if field == "cnpj" else ""
        digits = only_digits(value)
        if not is_valid_cnpj(digits):
            raise serializers.ValidationError("CNPJ inválido.")
        return digits

    def validate_cnpj(self, value):
        return self._clean_cnpj(value, "cnpj")

    def validate_ente_cnpj(self, value):
        return self._clean_cnpj(value, "ente_cnpj")

    def validate_cep(self, value):
        digits = only_digits(value)
        if digits and len(digits) != 8:
            raise serializers.ValidationError("CEP deve conter 8 dígitos.")
        return digits


class BenefitPlanSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = BenefitPlan
        fields = [
            "id", "code", "name", "kind", "kind_display", "description", "legal_basis",
            "start_date", "active", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_code(self, value):
        value = value.strip().upper()
        institution = self.context["request"].institution
        qs = BenefitPlan.objects.filter(institution=institution, code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Já existe um plano com este código.")
        return value


class PayrollGroupSerializer(serializers.ModelSerializer):
    segment_display = serializers.CharField(source="get_segment_display", read_only=True)
    plan_code = serializers.CharField(source="plan.code", read_only=True)
    plan_kind = serializers.CharField(source="plan.kind", read_only=True)

    class Meta:
        model = PayrollGroup
        fields = ["id", "segment", "segment_display", "code", "name", "plan", "plan_code", "plan_kind", "active"]
        read_only_fields = fields


class LifePurchaseSerializer(serializers.ModelSerializer):
    origin_plan_code = serializers.CharField(source="origin_plan.code", read_only=True)
    destination_plan_code = serializers.CharField(source="destination_plan.code", read_only=True)

    class Meta:
        model = LifePurchase
        fields = [
            "id", "number", "cutoff_date", "effective_date", "legal_act", "legal_act_date",
            "actuarial_study", "transferred_amount", "lives_count", "origin_plan", "origin_plan_code",
            "destination_plan", "destination_plan_code", "notes", "active", "created_at", "updated_at",
        ]
        read_only_fields = ["number", "created_at", "updated_at"]
        extra_kwargs = {"origin_plan": {"required": False}, "destination_plan": {"required": False}}

    def validate(self, attrs):
        from apps.core.exceptions import BusinessRuleError

        from . import services

        institution = self.context["request"].institution
        merged = {
            "origin_plan": getattr(self.instance, "origin_plan", None),
            "destination_plan": getattr(self.instance, "destination_plan", None),
            "cutoff_date": getattr(self.instance, "cutoff_date", None),
            "effective_date": getattr(self.instance, "effective_date", None),
            **attrs,
        }
        if merged["origin_plan"] is None:
            merged["origin_plan"] = attrs["origin_plan"] = services._plan_for(institution, "FINANCEIRO")
        if merged["destination_plan"] is None:
            merged["destination_plan"] = attrs["destination_plan"] = services._plan_for(institution, "PREVIDENCIARIO")
        try:
            services.validate_life_purchase(institution, merged, self.instance)
        except BusinessRuleError as exc:
            raise serializers.ValidationError({"non_field_errors": [str(exc)]})
        return attrs


class FiscalYearSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.CharField(source="closed_by.full_name", read_only=True, default="")
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    competences_count = serializers.IntegerField(source="competences.count", read_only=True)

    class Meta:
        model = FiscalYear
        fields = [
            "id", "year", "status", "status_display", "closed_at", "closed_by_name", "notes",
            "competences_count", "created_at",
        ]
        read_only_fields = ["status", "closed_at", "created_at"]

    def validate_year(self, value):
        if value < 1990 or value > 2100:
            raise serializers.ValidationError("Exercício fora do intervalo permitido.")
        institution = self.context["request"].institution
        qs = FiscalYear.objects.filter(institution=institution, year=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Exercício já cadastrado.")
        return value


class CompetenceSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)
    code = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    closed_by_name = serializers.CharField(source="closed_by.full_name", read_only=True, default="")

    class Meta:
        model = Competence
        fields = [
            "id", "year", "month", "code", "label", "status", "status_display", "is_reference",
            "closed_at", "closed_by_name", "created_at",
        ]
        read_only_fields = ["status", "is_reference", "closed_at", "created_at"]

    def get_code(self, obj):
        return f"{obj.month:02d}/{obj.year}"

    def validate_month(self, value):
        if not 1 <= value <= 12:
            raise serializers.ValidationError("Mês inválido.")
        return value


class ParameterSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = Parameter
        fields = [
            "id", "key", "value", "description", "version", "valid_from", "valid_to",
            "change_reason", "is_current", "created_by_name", "created_at",
        ]
        read_only_fields = ["version", "valid_to", "created_at"]

    def get_is_current(self, obj):
        from django.utils import timezone
        return obj.is_valid_on(timezone.localdate())

    def validate_key(self, value):
        value = value.strip().lower()
        import re
        if not re.fullmatch(r"[a-z0-9_.]{3,100}", value):
            raise serializers.ValidationError("Use apenas letras minúsculas, números, ponto e sublinhado.")
        return value
