import hashlib

from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import only_digits
from apps.core.views import InstitutionScopedMixin

from . import services
from .models import OPEN_STATUSES, Attachment, Holiday, Process, ProcessType, Sector
from .serializers import (
    AttachmentSerializer, HolidaySerializer, MovementSerializer, OpenProcessSerializer, ProcessSerializer,
    ProcessTypeSerializer, SectorSerializer,
)


class _ConfigViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    module_code = "protocolo.configuracao"

    def get_permissions(self):
        # Listas usadas nas telas de processos (abrir, tramitar)
        if self.action == "list":
            self.module_code = "protocolo.processos"
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("ativos") == "1":
            qs = qs.filter(active=True)
        return qs


class SectorViewSet(_ConfigViewSet):
    serializer_class = SectorSerializer
    queryset = Sector.objects.prefetch_related("members").select_related("organ").all()
    search_fields = ["name", "code"]

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """Setores do usuário logado (para abertura e caixa de entrada)."""
        qs = services.user_sectors(request.user, self.get_institution())
        return Response(SectorSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"])
    def destinos(self, request):
        """Todos os setores ativos — qualquer usuário do Protocolo pode abrir processo para eles."""
        qs = Sector.objects.filter(institution=self.get_institution(), active=True).order_by("code")
        mine = set(services.user_sectors(request.user, self.get_institution()).values_list("pk", flat=True))
        data = SectorSerializer(qs, many=True, context={"request": request}).data
        for row in data:
            row["meu"] = row["id"] in {str(x) for x in mine}
        return Response(data)

    def get_permissions(self):
        if self.action in ("mine", "destinos"):
            self.module_code = "protocolo.processos"
        return super().get_permissions()


class ProcessTypeViewSet(_ConfigViewSet):
    serializer_class = ProcessTypeSerializer
    queryset = ProcessType.objects.all()
    search_fields = ["name"]


class HolidayViewSet(_ConfigViewSet):
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.all()
    filterset_fields = ["kind"]
    pagination_class = None
    action_permissions = {"generate": "incluir"}

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get("ano")
        return qs.filter(date__year=int(year)) if year and year.isdigit() else qs

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Inclui os feriados nacionais e pontos facultativos usuais do ano (?ano=)."""
        try:
            year = int(request.data.get("year"))
            assert 1990 <= year <= 2100
        except (TypeError, ValueError, AssertionError):
            return Response({"year": ["Ano inválido."]}, status=400)
        created = services.generate_national_holidays(self.get_institution(), year)
        return Response({"criados": created})


class ProcessViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    """
    Processos do protocolo. Filtros: ?search= (número, assunto, interessado, CPF),
    ?caixa=entrada|setor|atrasados|todos, ?status=, ?setor=.
    Ações: abrir (POST), send, receive, despacho, suspend, resume, extend, conclude, archive, reopen.
    """

    module_code = "protocolo.processos"
    serializer_class = ProcessSerializer
    queryset = Process.objects.select_related("process_type", "current_sector").all()
    filterset_fields = ["status", "process_type", "priority", "interested"]
    ordering_fields = ["due_date", "opened_at", "number"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {
        "send": "editar", "receive": "editar", "despacho": "editar", "suspend": "editar", "resume": "editar",
        "extend": "editar", "conclude": "fechar", "archive": "fechar", "reopen": "reabrir", "movements": "visualizar",
        "attachments": "visualizar", "attach": "editar", "download": "visualizar",
    }

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if getattr(self.request, "institution", None) is not None:
            ctx["holidays"] = services.holidays_for(self.request.institution)
        return ctx

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        term = (p.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(subject__icontains=term) | Q(interested_name__icontains=term) | Q(external_number__icontains=term)
            if digits:
                cond |= Q(number=int(digits[:9])) | Q(interested_cpf__startswith=digits)
            if "/" in term:
                num, _, year = term.partition("/")
                if num.strip().isdigit() and year.strip().isdigit():
                    cond |= Q(number=int(num), year=int(year))
            qs = qs.filter(cond)
        caixa = p.get("caixa")
        mine = services.user_sectors(self.request.user, self.get_institution())
        if caixa == "entrada":
            qs = qs.filter(current_sector__in=mine, status__in=OPEN_STATUSES)
        elif caixa == "atrasados":
            qs = qs.filter(status__in=OPEN_STATUSES, due_date__lt=timezone.localdate(), suspended_since__isnull=True)
        if p.get("setor"):
            qs = qs.filter(current_sector_id=p["setor"])
        return qs.order_by(*(["due_date"] if caixa in ("entrada", "atrasados") else ["-year", "-number"]))

    def create(self, request, *args, **kwargs):
        ser = OpenProcessSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        process = services.open_process(request, **ser.validated_data)
        return Response(self.get_serializer(process).data, status=201)

    def _text(self):
        return (self.request.data.get("text") or "").strip()

    def _run(self, fn, *args):
        process = fn(self.request, self.get_object(), *args)
        return Response(self.get_serializer(process).data)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        sector = Sector.objects.filter(institution=self.get_institution(), pk=request.data.get("to_sector")).first()
        if sector is None:
            raise serializers.ValidationError({"to_sector": "Selecione o setor de destino."})
        return self._run(services.send, sector, self._text())

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        return self._run(services.receive)

    @action(detail=True, methods=["post"])
    def despacho(self, request, pk=None):
        # Não usar o nome "dispatch": sobrescreveria o método de roteamento do DRF
        return self._run(services.dispatch, self._text())

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        return self._run(services.suspend, self._text())

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return self._run(services.resume, self._text())

    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        try:
            days = int(request.data.get("days"))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"days": "Informe o número de dias."})
        return self._run(services.extend, days, self._text())

    @action(detail=True, methods=["post"])
    def conclude(self, request, pk=None):
        return self._run(services.close, self._text(), False)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return self._run(services.close, self._text(), True)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._run(services.reopen, self._text())

    @action(detail=True, methods=["get"])
    def movements(self, request, pk=None):
        process = self.get_object()
        qs = process.movements.select_related("from_sector", "to_sector", "created_by")
        return Response(MovementSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"])
    def attachments(self, request, pk=None):
        process = self.get_object()
        return Response(AttachmentSerializer(process.attachments.select_related("created_by"), many=True).data)

    @action(detail=True, methods=["post"])
    def attach(self, request, pk=None):
        process = self.get_object()
        if process.status not in OPEN_STATUSES:
            raise BusinessRuleError("Não é possível anexar a processo encerrado.")
        services.require_sector_member(request, process.current_sector)
        upload = request.FILES.get("file")
        description = (request.data.get("description") or "").strip()
        if upload is None or not description:
            raise serializers.ValidationError("Informe a descrição e selecione o arquivo.")
        from apps.people.services import ALLOWED_CONTENT_TYPES, MAX_DOCUMENT_BYTES

        if upload.size > MAX_DOCUMENT_BYTES or getattr(upload, "content_type", "") not in ALLOWED_CONTENT_TYPES:
            raise BusinessRuleError("Envie PDF, JPG ou PNG de até 10 MB.")
        content = upload.read()
        sha = hashlib.sha256(content).hexdigest()
        upload.seek(0)
        att = Attachment(institution=process.institution, process=process, description=description[:255],
                         file_name=upload.name[:255], file_size=len(content), content_type=upload.content_type,
                         sha256=sha)
        ext = "." + upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
        att.file.save(f"{sha[:16]}{ext}", upload, save=False)
        att.save()
        return Response(AttachmentSerializer(att).data, status=201)

    @action(detail=True, methods=["get"], url_path=r"attachments/(?P<att_id>[^/.]+)/download")
    def download(self, request, pk=None, att_id=None):
        process = self.get_object()
        att = process.attachments.filter(pk=att_id).first()
        if att is None:
            raise serializers.ValidationError("Anexo não encontrado.")
        log_event("EXPORT", module="protocolo.processos", obj=att, object_repr=f"Download {att.file_name}")
        return FileResponse(att.file.open("rb"), as_attachment=True, filename=att.file_name,
                            content_type=att.content_type)
