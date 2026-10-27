from rest_framework import serializers

from apps.core.validators import format_cpf

from . import services
from .models import RegistrationCampaign, Reregistration


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class CampaignSerializer(serializers.ModelSerializer):
    status_display = _display("status")
    audience_display = _display("audience")
    organ_name = serializers.CharField(source="organ.name", read_only=True, default="")
    stats = serializers.SerializerMethodField()

    class Meta:
        model = RegistrationCampaign
        exclude = ["institution", "updated_by"]
        read_only_fields = ["status", "opened_at", "closed_at", "created_by"]

    def get_stats(self, obj):
        return services.campaign_stats(obj)

    def validate(self, attrs):
        if self.instance is not None and self.instance.status != "RASCUNHO":
            if set(attrs) - {"instructions", "end_date", "portal_enabled"}:
                raise serializers.ValidationError("Campanha já aberta: só é possível alterar prazo final, orientações e o Portal.")
        return attrs


class ItemSerializer(serializers.ModelSerializer):
    status_display = _display("status")
    group_display = _display("group")
    channel_display = _display("channel")
    person_name = serializers.CharField(source="person.name", read_only=True)
    person_cpf = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, default="")
    mudancas = serializers.SerializerMethodField()
    has_residence = serializers.SerializerMethodField()
    has_id = serializers.SerializerMethodField()

    class Meta:
        model = Reregistration
        fields = ["id", "campaign", "campaign_name", "person", "person_name", "person_cpf", "phone", "group",
                  "group_display", "due_date", "status", "status_display", "channel", "channel_display", "submitted_at",
                  "proposed", "previous", "declarations", "review_note", "reviewed_by_name", "reviewed_at", "applied",
                  "staff_followup", "mudancas", "has_residence", "has_id"]

    def get_person_cpf(self, obj):
        return format_cpf(obj.person.cpf)

    def get_phone(self, obj):
        return obj.person.mobile or obj.person.phone

    def get_mudancas(self, obj):
        return services.changes(obj) if obj.status in ("ENVIADO", "APROVADO") else []

    def get_has_residence(self, obj):
        return bool(obj.residence_proof)

    def get_has_id(self, obj):
        return bool(obj.id_document)
