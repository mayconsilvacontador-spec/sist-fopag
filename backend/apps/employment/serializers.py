from django.utils import timezone
from datetime import date

from rest_framework import serializers

from apps.institutions.models import LifePurchase, Segment
from apps.institutions.services import active_segments

from .models import ABSENCE_EVENTS, EmploymentLink, EventType, FunctionalEvent, LinkStatus


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


class EmploymentLinkSerializer(serializers.ModelSerializer):
    person_name = serializers.CharField(source="person.name", read_only=True)
    person_cpf = serializers.CharField(source="person.cpf", read_only=True)
    organ_name = serializers.CharField(source="organ.__str__", read_only=True)
    position_name = serializers.CharField(source="position.name", read_only=True)
    initial_position_name = serializers.CharField(source="initial_position.name", read_only=True, default="")
    workplace_name = serializers.CharField(source="workplace.name", read_only=True, default="")
    career = serializers.CharField(source="position.career", read_only=True)
    link_type_display = _display("link_type")
    regime_display = _display("regime")
    admission_form_display = _display("admission_form")
    eligibility_display = _display("eligibility")
    situation_display = _display("situation")
    segment_display = _display("segment")
    status_display = _display("status")
    life_purchase_number = serializers.IntegerField(source="life_purchase.number", read_only=True, default=None)

    class Meta:
        model = EmploymentLink
        fields = [
            "id", "person", "person_name", "person_cpf", "organ", "organ_name", "position", "position_name", "career",
            "initial_position", "initial_position_name", "workplace", "workplace_name", "registration",
            "link_type", "link_type_display", "regime", "regime_display", "admission_form", "admission_form_display",
            "public_service_start", "ente_start", "career_start", "position_start", "statutory_since", "class_level",
            "base_salary", "weekly_hours", "eligibility", "eligibility_display", "situation", "situation_display", "segment",
            "segment_display", "life_purchase", "life_purchase_number", "permanence_bonus_since",
            "complementary_pension", "status", "status_display", "end_date", "end_reason", "notes",
            "created_at", "updated_at",
        ]
        # Encerramento só pela ação própria (registra o evento no histórico)
        read_only_fields = ["status", "end_date", "end_reason", "created_at", "updated_at"]

    def _get(self, attrs, name):
        return attrs.get(name, getattr(self.instance, name, None))

    def validate(self, attrs):
        inst = self.context["request"].institution
        errors = {}
        for fk in ("person", "organ", "position", "initial_position", "workplace", "life_purchase"):
            obj = attrs.get(fk)
            if obj is not None and obj.institution_id != inst.pk:
                errors[fk] = "Registro de outra instituição."
        organ, workplace = self._get(attrs, "organ"), self._get(attrs, "workplace")
        if workplace and organ and workplace.organ_id != organ.pk:
            errors["workplace"] = "A lotação não pertence ao órgão informado."

        person = self._get(attrs, "person")
        ps, es, cs, pos = (self._get(attrs, f) for f in ("public_service_start", "ente_start", "career_start",
                                                          "position_start"))
        if person and ps and ps <= person.birth_date:
            errors["public_service_start"] = "Ingresso no serviço público anterior ao nascimento."
        if ps and es and es < ps:
            errors["ente_start"] = "O ingresso no ente não pode ser anterior ao ingresso no serviço público."
        if es and pos and pos < es:
            errors["position_start"] = "O início no cargo não pode ser anterior ao ingresso no ente."
        if cs and es and cs < es:
            errors["career_start"] = "O ingresso na carreira não pode ser anterior ao ingresso no ente."
        if cs and pos and cs > pos:
            errors["career_start"] = "O ingresso na carreira não pode ser posterior ao início no cargo atual."
        if pos and pos > timezone.localdate():
            errors["position_start"] = "Data no futuro."

        segment = self._get(attrs, "segment")
        if segment and segment not in active_segments(inst):
            errors["segment"] = "Massa não disponível nesta instituição (verifique a Compra de Vidas)."
        lot = self._get(attrs, "life_purchase")
        if segment == Segment.COMPRA_VIDAS and lot is None:
            errors["life_purchase"] = "Informe o lote de Compra de Vidas que transferiu este servidor."
        if segment != Segment.COMPRA_VIDAS and lot is not None:
            attrs["life_purchase"] = None
        if isinstance(lot, LifePurchase) and not lot.active:
            errors["life_purchase"] = "Lote inativo."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class CloseLinkSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c for c in LinkStatus.choices if c[0] != LinkStatus.ATIVO])
    end_date = serializers.DateField()
    end_reason = serializers.CharField(max_length=255)
    act_type = serializers.CharField(max_length=30, required=False, allow_blank=True)
    act_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    act_date = serializers.DateField(required=False, allow_null=True)
    publication = serializers.CharField(max_length=120, required=False, allow_blank=True)


class FunctionalEventSerializer(serializers.ModelSerializer):
    event_type_display = _display("event_type")
    is_absence = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = FunctionalEvent
        fields = ["id", "link", "event_type", "event_type_display", "is_absence", "start_date", "end_date", "days",
                  "with_pay", "contributed", "counts_as_service", "act_type", "act_number", "act_date",
                  "publication", "description", "created_by_name", "created_at"]
        read_only_fields = ["created_at"]

    def get_is_absence(self, obj):
        return obj.event_type in ABSENCE_EVENTS

    def validate(self, attrs):
        inst = self.context["request"].institution
        link = attrs.get("link", getattr(self.instance, "link", None))
        if link and link.institution_id != inst.pk:
            raise serializers.ValidationError({"link": "Vínculo de outra instituição."})
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "O fim não pode ser anterior ao início."})
        if link and start and start < link.public_service_start:
            raise serializers.ValidationError({"start_date": "Evento anterior ao ingresso no serviço público."})
        etype = attrs.get("event_type", getattr(self.instance, "event_type", None))
        if etype == EventType.FALTAS and not attrs.get("days", getattr(self.instance, "days", None)):
            raise serializers.ValidationError({"days": "Informe o total de dias de faltas."})
        return attrs
