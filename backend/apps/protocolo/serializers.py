from rest_framework import serializers

from apps.core.validators import only_digits
from apps.people.models import Person

from .models import Attachment, Holiday, Movement, Priority, Process, ProcessType, Sector


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class SectorSerializer(serializers.ModelSerializer):
    organ_name = serializers.CharField(source="organ.__str__", read_only=True, default="")
    member_names = serializers.SerializerMethodField()

    class Meta:
        model = Sector
        fields = ["id", "name", "code", "organ", "organ_name", "members", "member_names", "active"]

    def get_member_names(self, obj):
        return [u.full_name for u in obj.members.all()]

    def validate_code(self, value):
        return value.strip().upper()

    def validate_organ(self, value):
        if value and value.institution_id != self.context["request"].institution.pk:
            raise serializers.ValidationError("Órgão de outra instituição.")
        return value

    def validate_members(self, users):
        from apps.accounts.models import Membership

        inst = self.context["request"].institution
        allowed = set(Membership.objects.filter(institution=inst, active=True).values_list("user_id", flat=True))
        if any(u.pk not in allowed for u in users):
            raise serializers.ValidationError("Há usuários sem acesso a esta instituição.")
        return users


class ProcessTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessType
        fields = ["id", "name", "deadline_days", "business_days", "sector_deadline_days", "description", "active"]


class HolidaySerializer(serializers.ModelSerializer):
    kind_display = _display("kind")

    class Meta:
        model = Holiday
        fields = ["id", "date", "name", "kind", "kind_display", "active"]


class MovementSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    from_sector_code = serializers.CharField(source="from_sector.code", read_only=True, default="")
    to_sector_code = serializers.CharField(source="to_sector.code", read_only=True, default="")
    user_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = Movement
        fields = ["id", "kind", "kind_display", "from_sector", "from_sector_code", "to_sector", "to_sector_code",
                  "text", "occurred_at", "due_date_after", "user_name"]


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = Attachment
        fields = ["id", "process", "description", "file_name", "file_size", "content_type", "sha256", "uploaded_by",
                  "created_at"]


class ProcessSerializer(serializers.ModelSerializer):
    code = serializers.CharField(read_only=True)
    process_type_name = serializers.CharField(source="process_type.name", read_only=True)
    current_sector_code = serializers.CharField(source="current_sector.code", read_only=True)
    current_sector_name = serializers.CharField(source="current_sector.name", read_only=True)
    status_display = _display("status")
    priority_display = _display("priority")
    prazo = serializers.SerializerMethodField()

    class Meta:
        model = Process
        fields = ["id", "code", "number", "year", "process_type", "process_type_name", "subject", "description",
                  "interested", "interested_name", "interested_cpf", "priority", "priority_display",
                  "external_number", "status", "status_display", "current_sector", "current_sector_code",
                  "current_sector_name", "pending_receipt", "opened_at", "opened_date", "business_days",
                  "deadline_days", "due_date", "sector_due_date", "suspended_since", "closed_at", "prazo"]
        read_only_fields = fields

    def get_prazo(self, obj):
        from .services import deadline_info

        hol = self.context.get("holidays")
        return deadline_info(obj, hol) if hol is not None else None


class OpenProcessSerializer(serializers.Serializer):
    process_type = serializers.PrimaryKeyRelatedField(queryset=ProcessType.objects.all())
    sector = serializers.PrimaryKeyRelatedField(queryset=Sector.objects.all())
    subject = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    interested = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), required=False, allow_null=True)
    interested_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    interested_cpf = serializers.CharField(max_length=18, required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=Priority.choices, default=Priority.NORMAL)
    external_number = serializers.CharField(max_length=40, required=False, allow_blank=True)

    def validate(self, attrs):
        inst = self.context["request"].institution
        for f in ("process_type", "sector", "interested"):
            obj = attrs.get(f)
            if obj is not None and obj.institution_id != inst.pk:
                raise serializers.ValidationError({f: "Registro de outra instituição."})
        if not attrs.get("interested") and not (attrs.get("interested_name") or "").strip():
            raise serializers.ValidationError({"interested_name": "Informe o interessado."})
        attrs["interested_cpf"] = only_digits(attrs.get("interested_cpf"))
        return attrs
