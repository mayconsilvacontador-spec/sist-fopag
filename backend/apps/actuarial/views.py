from django.http import FileResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import log_event
from apps.core.views import InstitutionScopedMixin

from . import generator, layouts
from .models import ActuarialBase


class ActuarialBaseSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    data_base = serializers.SerializerMethodField()

    class Meta:
        model = ActuarialBase
        fields = [
            "id", "reference_year", "reference_month", "data_base", "layout_code", "life_purchase_enabled",
            "file_name", "file_sha256", "file_size", "summary", "pendencias", "notes",
            "created_by_name", "created_at",
        ]
        read_only_fields = [f for f in fields if f not in ("reference_year", "reference_month", "notes")]

    def get_data_base(self, obj):
        return f"{obj.reference_month:02d}/{obj.reference_year}"


class ActuarialBaseViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    Bases atuariais geradas. POST gera uma nova base (nunca sobrescreve).
    GET {id}/download/ baixa o ZIP; GET layout/ devolve o dicionário do leiaute.
    """

    module_code = "atuarial.base"
    serializer_class = ActuarialBaseSerializer
    queryset = ActuarialBase.objects.select_related("created_by").all()
    action_permissions = {"download": "exportar", "layout": "visualizar"}

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        base = generator.generate(self.get_institution(), d["reference_year"], d["reference_month"], d.get("notes", ""))
        return Response(self.get_serializer(base).data, status=201)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        base = self.get_object()
        log_event("EXPORT", module="atuarial.base", obj=base,
                  object_repr=f"Download {base.file_name}", extra={"sha256": base.file_sha256})
        return FileResponse(base.file.open("rb"), as_attachment=True, filename=base.file_name,
                            content_type="application/zip")

    @action(detail=False, methods=["get"])
    def layout(self, request):
        data = layouts.load_layout()
        return Response({
            "codigo": data["codigo"], "nome": data["nome"], "fonte": data["fonte"], "observacao": data["observacao"],
            "arquivos": [
                {"chave": key, "arquivo": name, "rotulo": label, "baixas": baixa, "variaveis": data["arquivos"][key]}
                for key, (name, label, baixa) in layouts.FILES.items()
            ],
        })
