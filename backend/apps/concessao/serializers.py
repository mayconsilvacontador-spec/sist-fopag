from rest_framework import serializers

from apps.core.validators import format_cpf

from .models import (
    Benefit, BenefitEvent, ChecklistItem, ChecklistTemplate, Concession, ConcessionDocument, ConcessionStep,
    DocumentTemplate, Parcel, PensionQuota,
)


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class ParcelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcel
        fields = ["id", "kind", "name", "legal_basis", "correlation", "percent", "proportionality", "amount",
                  "in_reference"]


class QuotaSerializer(serializers.ModelSerializer):
    dependent_name = serializers.CharField(source="dependent.name", read_only=True)
    dependent_cpf = serializers.SerializerMethodField()
    relation_display = _display("relation")
    duration_display = _display("duration")

    class Meta:
        model = PensionQuota
        fields = ["id", "dependent", "dependent_name", "dependent_cpf", "relation", "relation_display", "percent",
                  "amount", "duration", "duration_display", "end_date", "duration_basis"]

    def get_dependent_cpf(self, obj):
        return format_cpf(obj.dependent.cpf)


class ConcessionSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    stage_display = _display("stage")
    modality_display = _display("modality")
    validity_class_display = _display("validity_class")
    act_nature_display = _display("act_nature")
    person_name = serializers.CharField(source="person.name", read_only=True)
    person_cpf = serializers.SerializerMethodField()
    process_code = serializers.CharField(source="process.code", read_only=True)
    rule_code = serializers.CharField(source="rule.code", read_only=True, default="")
    rule_name = serializers.CharField(source="rule.name", read_only=True, default="")
    link_label = serializers.SerializerMethodField()
    approved_by_name = serializers.CharField(source="approved_by.full_name", read_only=True, default="")
    revised_benefit_label = serializers.SerializerMethodField()
    tce_result_display = _display("tce_result")
    parcels = ParcelSerializer(many=True, read_only=True)
    quotas = QuotaSerializer(many=True, read_only=True)
    suspended_from_display = serializers.SerializerMethodField()

    class Meta:
        model = Concession
        exclude = ["institution", "updated_by"]

    def get_suspended_from_display(self, obj):
        from .models import Stage

        return Stage(obj.suspended_from).label if obj.suspended_from else ""

    def get_person_cpf(self, obj):
        return format_cpf(obj.person.cpf)

    def get_revised_benefit_label(self, obj):
        b = obj.revised_benefit
        return f"{b.get_kind_display()} de {b.beneficiary.name} — R$ {b.amount}" if b else ""

    def get_link_label(self, obj):
        lk = obj.link
        return f"{lk.registration} — {lk.position.name} ({lk.organ})" if lk else ""


class ConcessionListSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    stage_display = _display("stage")
    person_name = serializers.CharField(source="person.name", read_only=True)
    process_code = serializers.CharField(source="process.code", read_only=True)
    rule_name = serializers.CharField(source="rule.name", read_only=True, default="")

    class Meta:
        model = Concession
        fields = ["id", "kind", "kind_display", "stage", "stage_display", "person", "person_name", "process",
                  "process_code", "rule_name", "validity_date", "total", "created_at"]


class BenefitEventSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    user_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = BenefitEvent
        fields = ["id", "kind", "kind_display", "date", "justification", "act", "old_values", "new_values",
                  "user_name", "created_at"]


class BenefitSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    modality_display = _display("modality")
    status_display = _display("status")
    beneficiary_name = serializers.CharField(source="beneficiary.name", read_only=True)
    beneficiary_cpf = serializers.SerializerMethodField()
    instituidor_name = serializers.CharField(source="instituidor.name", read_only=True, default="")
    folha = serializers.CharField(source="payroll_group.code", read_only=True)
    folha_name = serializers.CharField(source="payroll_group.name", read_only=True)
    concession_process = serializers.CharField(source="concession.process.code", read_only=True, default="")
    imported = serializers.SerializerMethodField()

    class Meta:
        model = Benefit
        fields = ["id", "kind", "kind_display", "modality", "modality_display", "beneficiary", "beneficiary_name",
                  "beneficiary_cpf", "instituidor", "instituidor_name", "concession", "concession_process", "imported",
                  "folha", "folha_name", "registration", "legal_basis", "start_date", "end_date", "amount", "percent",
                  "integralidade", "paridade", "status", "status_display", "esocial_nr", "esocial_tp_beneficio",
                  "esocial_mtv_termino"]

    def get_beneficiary_cpf(self, obj):
        return format_cpf(obj.beneficiary.cpf)

    def get_imported(self, obj):
        return obj.legacy_id is not None


class StepSerializer(serializers.ModelSerializer):
    action_display = _display("action")
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = ConcessionStep
        fields = ["id", "action", "action_display", "role", "stage_from", "stage_to", "user_name", "text", "data",
                  "signed", "signature_hash", "created_at"]


class DocumentSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="Sistema")

    class Meta:
        model = ConcessionDocument
        fields = ["id", "kind", "kind_display", "version", "file_name", "sha256", "created_by_name", "created_at"]


class TemplateSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    concession_kind_display = _display("concession_kind")

    class Meta:
        model = DocumentTemplate
        exclude = ["institution", "updated_by"]


class ChecklistTemplateSerializer(serializers.ModelSerializer):
    concession_kind_display = _display("concession_kind")
    sector_display = _display("sector")
    source_display = _display("source")
    modality_display = _display("modality")

    class Meta:
        model = ChecklistTemplate
        exclude = ["institution", "updated_by"]

    def validate(self, attrs):
        src = attrs.get("source", getattr(self.instance, "source", "ANEXO"))
        if src == "SISTEMA" and not attrs.get("system_kind", getattr(self.instance, "system_kind", "")):
            raise serializers.ValidationError({"system_kind": "Informe qual documento o sistema gera."})
        return attrs


class ChecklistItemSerializer(serializers.ModelSerializer):
    sector_display = _display("sector")
    status_display = _display("status")
    source_display = _display("source")
    file_name = serializers.SerializerMethodField()
    file_id = serializers.SerializerMethodField()
    done_by_name = serializers.CharField(source="done_by.full_name", read_only=True, default="")

    class Meta:
        model = ChecklistItem
        fields = ["id", "sector", "sector_display", "name", "help_text", "source", "source_display", "system_kind",
                  "required", "status", "status_display", "sha256", "note", "file_name", "file_id", "done_by_name",
                  "done_at", "attachment", "document", "person_doc_type", "person_document"]

    def get_file_name(self, obj):
        return obj.attachment.file_name if obj.attachment_id else (obj.document.file_name if obj.document_id else "")

    def get_file_id(self, obj):
        return str(obj.attachment_id or obj.document_id or "")