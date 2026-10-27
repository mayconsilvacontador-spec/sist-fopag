from django.db.models import Case, Count, IntegerField, Value, When
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.views import InstitutionScopedMixin

from . import services
from .models import Alert, AlertStatus, Severity


def _by_group(qs) -> dict:
    out: dict[str, dict] = {}
    for module, severity, n in qs.values_list("module", "severity").annotate(n=Count("id")):
        g = out.setdefault((module or "").split(".")[0], {"total": 0, "critico": 0})
        g["total"] += n
        if severity == Severity.CRITICO:
            g["critico"] += n
    return out


class AlertSerializer(serializers.ModelSerializer):
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    resolved_by_name = serializers.CharField(source="resolved_by.full_name", read_only=True, default="")

    class Meta:
        model = Alert
        fields = [
            "id", "severity", "severity_display", "code", "module", "title", "message", "link",
            "object_type", "object_id", "is_demo", "status", "status_display", "detected_at",
            "last_seen_at", "resolved_at", "resolved_by_name", "resolution_note",
        ]
        read_only_fields = fields


class AlertViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                   viewsets.GenericViewSet):
    module_code = "alertas"
    serializer_class = AlertSerializer
    queryset = Alert.objects.select_related("resolved_by").all()
    filterset_fields = ["severity", "status", "module", "is_demo"]
    search_fields = ["title", "message"]
    action_permissions = {"resolve": "editar", "run_checks": "editar", "summary": "visualizar"}

    def get_queryset(self):
        qs = super().get_queryset()
        if "status" not in self.request.query_params:
            qs = qs.filter(status=AlertStatus.ABERTO)
        order = Case(
            When(severity=Severity.CRITICO, then=Value(0)),
            When(severity=Severity.ATENCAO, then=Value(1)),
            default=Value(2), output_field=IntegerField(),
        )
        return qs.annotate(sev_order=order).order_by("sev_order", "-detected_at")

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        alert = services.resolve_alert(
            self.get_object(), request.user, request.data.get("note", ""),
            discard=bool(request.data.get("discard")),
        )
        return Response(self.get_serializer(alert).data)

    @action(detail=False, methods=["post"], url_path="run-checks")
    def run_checks(self, request):
        stats = services.run_checks(self.get_institution())
        return Response(stats)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = Alert.objects.filter(institution=self.get_institution(), status=AlertStatus.ABERTO)
        counts = {row["severity"]: row["n"] for row in qs.values("severity").annotate(n=Count("id"))}
        return Response({
            "total": sum(counts.values()),
            "CRITICO": counts.get(Severity.CRITICO, 0),
            "ATENCAO": counts.get(Severity.ATENCAO, 0),
            "INFORMATIVO": counts.get(Severity.INFORMATIVO, 0),
            "demo": qs.filter(is_demo=True).count(),
            # Pendências por grupo do menu (prefixo do módulo: "concessao.juridico" -> "concessao")
            "por_grupo": _by_group(qs),
        })
