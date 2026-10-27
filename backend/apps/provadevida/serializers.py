from rest_framework import serializers

from apps.core.validators import format_cpf

from . import services
from .models import LifeProof, LifeProofCampaign


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class CampaignSerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    status_display = _display("status")
    deadline_rule_display = _display("deadline_rule")
    audience_display = _display("audience")
    stats = serializers.SerializerMethodField()

    class Meta:
        model = LifeProofCampaign
        exclude = ["institution", "updated_by"]
        read_only_fields = ["status", "opened_at", "closed_at", "created_by"]

    def get_stats(self, obj):
        return services.campaign_stats(obj)

    def validate(self, attrs):
        if self.instance is not None and self.instance.status != "RASCUNHO":
            allowed = {"instructions", "portal_notice", "grace_days", "end_date"}
            if set(attrs) - allowed:
                raise serializers.ValidationError("Campanha já aberta: só é possível alterar prazo final, tolerância e "
                                                  "orientações.")
        return attrs


class ProofSerializer(serializers.ModelSerializer):
    status_display = _display("status")
    channel_display = _display("channel")
    person_name = serializers.CharField(source="person.name", read_only=True)
    person_cpf = serializers.SerializerMethodField()
    birth_date = serializers.DateField(source="person.birth_date", read_only=True)
    phone = serializers.SerializerMethodField()
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    registered_by_name = serializers.CharField(source="registered_by.full_name", read_only=True, default="")
    has_attachment = serializers.SerializerMethodField()
    days_late = serializers.SerializerMethodField()

    class Meta:
        model = LifeProof
        fields = ["id", "campaign", "campaign_name", "person", "person_name", "person_cpf", "birth_date", "phone",
                  "due_date", "status", "status_display", "done_date", "channel", "channel_display", "notes",
                  "registered_by_name", "has_attachment", "attachment_sha256", "suspended_at", "days_late",
                  "portal_submitted_at", "status_before_portal", "review_note", "has_portal_photos", "portal_liveness",
                  "frames_count"]

    def get_person_cpf(self, obj):
        return format_cpf(obj.person.cpf)

    def get_phone(self, obj):
        return obj.person.mobile or obj.person.phone

    has_portal_photos = serializers.SerializerMethodField()

    frames_count = serializers.SerializerMethodField()

    def get_frames_count(self, obj):
        return len(obj.portal_frames or [])

    def get_has_portal_photos(self, obj):
        return bool(obj.portal_selfie)

    def get_has_attachment(self, obj):
        return bool(obj.attachment)

    def get_days_late(self, obj):
        from django.utils import timezone

        if obj.status not in ("PENDENTE", "BLOQUEADO", "EM_ANALISE"):
            return None
        return max(0, (timezone.localdate() - obj.due_date).days)
