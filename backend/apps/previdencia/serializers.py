from datetime import date

from rest_framework import serializers

from apps.core.validators import only_digits

from .models import Averbacao, ContributionSalary, Ctc, RetirementRule

EC103_DATE = date(2019, 11, 12)  # vedada a conversão de tempo especial em comum após a EC 103


class AverbacaoSerializer(serializers.ModelSerializer):
    nature_display = serializers.CharField(source="get_nature_display", read_only=True)
    is_public_service = serializers.BooleanField(read_only=True)
    gross_days = serializers.SerializerMethodField()

    class Meta:
        model = Averbacao
        fields = ["id", "person", "nature", "nature_display", "issuer", "issuer_cnpj", "certificate_number",
                  "certificate_date", "start_date", "end_date", "gross_days", "certified_days", "magisterio",
                  "special_activity", "conversion_extra_days", "act_number", "act_date", "comprev", "notes", "active",
                  "is_public_service"]

    def get_gross_days(self, obj):
        return (obj.end_date - obj.start_date).days + 1

    def validate_issuer_cnpj(self, value):
        return only_digits(value)

    def validate(self, attrs):
        inst = self.context["request"].institution
        person = attrs.get("person", getattr(self.instance, "person", None))
        if person and person.institution_id != inst.pk:
            raise serializers.ValidationError({"person": "Pessoa de outra instituição."})
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end:
            if end < start:
                raise serializers.ValidationError({"end_date": "O fim não pode ser anterior ao início."})
            gross = (end - start).days + 1
            cert = attrs.get("certified_days", getattr(self.instance, "certified_days", 0))
            if cert > gross:
                raise serializers.ValidationError({"certified_days": f"Maior que o período ({gross} dias)."})
            extra = attrs.get("conversion_extra_days", getattr(self.instance, "conversion_extra_days", 0))
            if extra and start > EC103_DATE:
                raise serializers.ValidationError(
                    {"conversion_extra_days": "Conversão de tempo especial vedada após 12/11/2019 (EC 103)."})
        return attrs


class ContributionSalarySerializer(serializers.ModelSerializer):
    competencia = serializers.SerializerMethodField()

    class Meta:
        model = ContributionSalary
        fields = ["id", "person", "competence", "competencia", "regime", "source_label", "amount", "origin"]
        read_only_fields = ["origin"]

    def get_competencia(self, obj):
        return obj.competence.strftime("%m/%Y")

    def validate_competence(self, value):
        value = value.replace(day=1)
        if value.year < 1994 or (value.year == 1994 and value.month < 7):
            raise serializers.ValidationError("Competência anterior a 07/1994.")
        return value

    def validate(self, attrs):
        person = attrs.get("person", getattr(self.instance, "person", None))
        if person and person.institution_id != self.context["request"].institution.pk:
            raise serializers.ValidationError({"person": "Pessoa de outra instituição."})
        return attrs


class RetirementRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetirementRule
        fields = ["id", "code", "name", "legal_basis", "engine", "group", "for_teacher", "params", "valid_from",
                  "valid_to", "proventos", "paridade", "gives_permanence_bonus", "notes", "active", "updated_at"]
        read_only_fields = ["code", "engine", "updated_at"]


class CtcSerializer(serializers.ModelSerializer):
    code = serializers.CharField(read_only=True)
    person_name = serializers.CharField(source="person.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    issued_by = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    process_code = serializers.CharField(source="process.code", read_only=True, default="")

    class Meta:
        model = Ctc
        fields = ["id", "code", "number", "year", "person", "person_name", "destination", "purpose", "period_start",
                  "period_end", "snapshot", "sha256", "process", "process_code", "status", "status_display",
                  "cancel_reason", "issued_by", "created_at"]
        read_only_fields = fields
