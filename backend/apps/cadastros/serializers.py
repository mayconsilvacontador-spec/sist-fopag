from rest_framework import serializers

from apps.core.validators import format_cnpj, is_valid_cnpj, only_digits

from .models import Bank, BankBranch, Ente, Organ, Position, Workplace


class ScopedSerializer(serializers.ModelSerializer):
    """
    Base dos cadastros: valida que as FKs pertencem à instituição corrente e
    normaliza CNPJ (aceita com máscara, grava só dígitos).
    """

    scoped_fks: tuple = ()

    def validate(self, attrs):
        institution = self.context["request"].institution
        for name in self.scoped_fks:
            obj = attrs.get(name)
            if obj is not None and obj.institution_id != institution.pk:
                raise serializers.ValidationError({name: "Registro de outra instituição."})
        return attrs

    def validate_cnpj(self, value):
        digits = only_digits(value)
        if digits and not is_valid_cnpj(digits):
            raise serializers.ValidationError("CNPJ inválido.")
        return digits


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class EnteSerializer(ScopedSerializer):
    kind_display = _display("kind")
    cnpj_formatado = serializers.SerializerMethodField()

    class Meta:
        model = Ente
        fields = ["id", "name", "kind", "kind_display", "cnpj", "cnpj_formatado", "ibge_code", "uf", "active"]

    def get_cnpj_formatado(self, obj):
        return format_cnpj(obj.cnpj)


class OrganSerializer(ScopedSerializer):
    scoped_fks = ("ente",)
    ente_name = serializers.CharField(source="ente.name", read_only=True)
    poder_display = _display("poder")
    tipo_poder_display = _display("tipo_poder")
    cnpj_formatado = serializers.SerializerMethodField()

    class Meta:
        model = Organ
        fields = ["id", "ente", "ente_name", "name", "short_name", "cnpj", "cnpj_formatado", "poder", "poder_display",
                  "tipo_poder", "tipo_poder_display", "sigfis_code", "active"]

    def get_cnpj_formatado(self, obj):
        return format_cnpj(obj.cnpj)

    def validate_sigfis_code(self, value):
        digits = only_digits(value)
        if digits and len(digits) > 4:
            raise serializers.ValidationError("O código SIGFIS tem até 4 dígitos.")
        return digits


class PositionSerializer(ScopedSerializer):
    cargo_type_display = _display("cargo_type")

    class Meta:
        model = Position
        fields = ["id", "name", "career", "cargo_type", "cargo_type_display", "cbo", "education", "weekly_hours",
                  "legal_basis", "active"]


class WorkplaceSerializer(ScopedSerializer):
    scoped_fks = ("organ",)
    organ_name = serializers.CharField(source="organ.__str__", read_only=True)

    class Meta:
        model = Workplace
        fields = ["id", "organ", "organ_name", "name", "code", "active"]


class BankSerializer(ScopedSerializer):
    class Meta:
        model = Bank
        fields = ["id", "code", "name", "active"]

    def validate_code(self, value):
        digits = only_digits(value)
        if len(digits) != 3:
            raise serializers.ValidationError("O código do banco tem 3 dígitos.")
        return digits


class BankBranchSerializer(ScopedSerializer):
    scoped_fks = ("bank",)
    bank_label = serializers.CharField(source="bank.__str__", read_only=True)

    class Meta:
        model = BankBranch
        fields = ["id", "bank", "bank_label", "number", "digit", "name", "city", "uf", "active"]

    def validate_number(self, value):
        digits = only_digits(value)
        if not digits:
            raise serializers.ValidationError("Informe o número da agência.")
        return digits
