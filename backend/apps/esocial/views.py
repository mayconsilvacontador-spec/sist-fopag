from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import has_perm
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import only_digits
from apps.core.views import InstitutionScopedMixin

from . import services
from .builders import ROOTS
from .models import EsocialBatch, EsocialEvent, EsocialLog
from .validation import xsd_available


def _require(request, *perms: str):
    if not any(has_perm(request, p) for p in perms):
        raise PermissionDenied("Você não possui permissão para esta operação do eSocial.")


class EventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    replaces_event_id = serializers.CharField(source="replaces.event_id", read_only=True, default="")
    replaced = serializers.SerializerMethodField()

    class Meta:
        model = EsocialEvent
        exclude = ["institution", "updated_by", "xml"]

    def get_replaced(self, obj):
        return obj.replaced_by.exists()


class LogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True, default="")
    event_type = serializers.CharField(source="event.event_type", read_only=True)
    event_reference = serializers.CharField(source="event.reference", read_only=True)
    event_id = serializers.CharField(source="event.event_id", read_only=True)
    event = serializers.CharField(source="event.pk", read_only=True)

    class Meta:
        model = EsocialLog
        fields = ["id", "event", "event_id", "event_type", "event_reference", "action", "detail", "user_name",
                  "created_at"]


class EventViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Eventos do eSocial RPPS. Gerar: generate-registrations, generate-rubrics, generate-payroll {run}, close-period
    {period}. Por evento: xml, revalidate, replace, return {accepted, receipt, code, message}. export {ids} (ZIP),
    import-return (arquivo XML de retorno), summary.
    """

    module_code = "esocial.eventos"
    serializer_class = EventSerializer
    queryset = EsocialEvent.objects.select_related("replaces").all()
    filterset_fields = ["event_type", "status", "period"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {a: "visualizar" for a in (
        "generate_registrations", "generate_rubrics", "generate_payroll", "close_period", "revalidate", "replace",
        "register_return", "export", "import_return", "summary", "xml", "logs", "history")}

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        term = (p.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(reference__icontains=term) | Q(event_id__icontains=term) | Q(receipt__icontains=term)
            if len(digits) >= 3:
                cond |= Q(cpf__startswith=digits)
            qs = qs.filter(cond)
        tipos = [t for t in (p.get("tipos") or "").split(",") if t]
        if tipos:
            qs = qs.filter(event_type__in=tipos)
        situacoes = [s for s in (p.get("situacoes") or "").split(",") if s]
        if situacoes:
            qs = qs.filter(status__in=situacoes)
        return qs

    def retrieve(self, request, *args, **kwargs):
        ev = self.get_object()
        data = EventSerializer(ev).data
        data["xml"] = ev.xml
        data["xsd_disponivel"] = xsd_available(ROOTS[ev.event_type])
        data["logs"] = LogSerializer(ev.logs.select_related("user"), many=True).data
        return Response(data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        _require(request, "esocial.painel:visualizar", "esocial.eventos:visualizar")
        inst = self.get_institution()
        return Response({"por_evento": services.summary(inst),
                         "xsd": {t: xsd_available(r) for t, r in ROOTS.items()}})

    @action(detail=False, methods=["post"], url_path="generate-registrations")
    def generate_registrations(self, request):
        _require(request, "esocial.s2400:incluir", "esocial.s2410:incluir")
        return Response(services.generate_registrations(self.get_institution(), request.user))

    @action(detail=False, methods=["post"], url_path="generate-rubrics")
    def generate_rubrics(self, request):
        _require(request, "esocial.s1207:incluir")
        return Response(services.generate_rubrics(self.get_institution(), request.user))

    @action(detail=False, methods=["post"], url_path="generate-payroll")
    def generate_payroll(self, request):
        from apps.folha.models import PayrollRun

        _require(request, "esocial.s1207:incluir")
        run = PayrollRun.objects.filter(institution=self.get_institution(), pk=request.data.get("run")).first()
        if run is None:
            raise serializers.ValidationError({"run": "Escolha a folha."})
        return Response(services.generate_payroll(run, request.user))

    @action(detail=False, methods=["post"], url_path="close-period")
    def close_period(self, request):
        _require(request, "esocial.s1207:aprovar")
        ev = services.close_period(self.get_institution(), str(request.data.get("period") or ""), request.user)
        return Response(EventSerializer(ev).data, status=201)

    @action(detail=True, methods=["post"])
    def revalidate(self, request, pk=None):
        _require(request, "esocial.pendencias:editar")
        return Response(EventSerializer(services.revalidate(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def replace(self, request, pk=None):
        _require(request, "esocial.rejeicoes:editar")
        return Response(EventSerializer(services.replace(self.get_object(), request.user)).data, status=201)

    @action(detail=True, methods=["post"], url_path="return")
    def register_return(self, request, pk=None):
        _require(request, "esocial.retornos:incluir")
        d = request.data
        ev = services.register_return(self.get_object(), accepted=str(d.get("accepted")).lower() in ("true", "1"),
                                      receipt=d.get("receipt", ""), code=d.get("code", ""),
                                      message=d.get("message", ""), user=request.user)
        return Response(EventSerializer(ev).data)

    @action(detail=False, methods=["post"])
    def export(self, request):
        _require(request, "esocial.eventos:exportar")
        ids = request.data.get("ids") or []
        events = list(self.get_queryset().filter(pk__in=ids))
        if not events:
            raise BusinessRuleError("Selecione os eventos a exportar.")
        content = services.export(events, request.user)
        name = f"esocial-{timezone.localtime():%Y%m%d-%H%M%S}.zip"
        resp = HttpResponse(content, content_type="application/zip")
        resp["Content-Disposition"] = f'attachment; filename="{name}"'
        return resp

    @action(detail=False, methods=["post"], url_path="import-return")
    def import_return(self, request):
        _require(request, "esocial.retornos:incluir")
        f = request.FILES.get("file")
        if f is None:
            raise serializers.ValidationError({"file": "Envie o arquivo XML de retorno."})
        if f.size > 20 * 1024 * 1024:
            raise BusinessRuleError("Arquivo muito grande (máx. 20 MB).")
        return Response(services.import_returns(self.get_institution(), f.read(), request.user))

    @action(detail=True, methods=["get"])
    def xml(self, request, pk=None):
        ev = self.get_object()
        resp = HttpResponse(ev.xml, content_type="application/xml; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{ev.event_id}.xml"'
        return resp

    @action(detail=False, methods=["get"])
    def history(self, request):
        _require(request, "esocial.historico:visualizar")
        qs = EsocialLog.objects.filter(institution=self.get_institution()).select_related("event", "user")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(LogSerializer(page, many=True).data)


# ================================================================== transmissão direta
class BatchSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    group_display = serializers.CharField(source="get_group_display", read_only=True)
    environment_display = serializers.CharField(source="get_environment_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    total = serializers.SerializerMethodField()
    resumo = serializers.SerializerMethodField()

    class Meta:
        model = EsocialBatch
        fields = ["id", "environment", "environment_display", "group", "group_display", "status", "status_display",
                  "protocol", "sent_at", "response_code", "response_message", "queried_at", "queries",
                  "request_sha256", "created_by_name", "total", "resumo"]

    def get_total(self, o):
        return o.events.count()

    def get_resumo(self, o):
        from django.db.models import Count

        return {r["status"]: r["n"] for r in o.events.values("status").order_by().annotate(n=Count("id"))}


class TransmissionView(InstitutionScopedMixin, viewsets.ViewSet):
    """
    GET  esocial/transmissao/            certificado ativo, ambiente e eventos prontos por grupo
    POST esocial/transmissao/certificado/ {arquivo, senha_certificado, password}  instala o A1
    POST esocial/transmissao/testar/      apresenta o certificado ao eSocial (sem enviar eventos)
    POST esocial/transmissao/transmitir/  {ids, password}  assina e envia um lote
    """

    module_code = "esocial.transmissao"
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {"list": "visualizar", "certificado": "editar", "testar": "editar", "transmitir": "incluir"}

    def list(self, request):
        from django.conf import settings
        from django.db.models import Count

        from . import transmission as tx
        from .builders import Ctx

        inst = self.get_institution()
        ready = {1: 0, 2: 0, 3: 0}
        for r in (EsocialEvent.objects.filter(institution=inst, status="VALIDADO").values("event_type")
                  .order_by().annotate(n=Count("id"))):
            ready[tx.GROUP_BY_TYPE[r["event_type"]]] += r["n"]
        env = Ctx.load(inst).environment
        return Response({"certificado": tx.certificate_info(tx.active_certificate(inst)),
                         "ambiente": env, "ambiente_display": "Produção" if env == 1 else "Produção restrita (testes)",
                         "chave_configurada": bool(getattr(settings, "ESOCIAL_CERT_KEY", "")),
                         "prontos": {tx.GROUP_LABEL[g]: n for g, n in ready.items()}, "limite_lote": tx.MAX_EVENTS})

    @action(detail=False, methods=["post"])
    def certificado(self, request):
        from apps.concessao.workflow import confirm_password

        from . import transmission as tx

        confirm_password(request.user, request.data.get("password", ""))
        f = request.FILES.get("arquivo")
        if f is None:
            raise serializers.ValidationError({"arquivo": "Envie o arquivo .pfx do certificado."})
        c, warnings = tx.install_certificate(self.get_institution(), f.read(), request.data.get("senha_certificado", ""),
                                             request.user)
        return Response({"certificado": tx.certificate_info(c), "avisos": warnings}, status=201)

    @action(detail=False, methods=["post"])
    def testar(self, request):
        from . import transmission as tx

        return Response(tx.test_connection(self.get_institution()))

    @action(detail=False, methods=["post"])
    def transmitir(self, request):
        from apps.concessao.workflow import confirm_password

        from . import transmission as tx

        confirm_password(request.user, request.data.get("password", ""))
        ids = request.data.get("ids") or []
        events = list(EsocialEvent.objects.filter(institution=self.get_institution(), pk__in=ids).order_by("created_at"))
        if len(events) != len(set(ids)):
            raise serializers.ValidationError({"ids": "Eventos inválidos."})
        b = tx.transmit(self.get_institution(), events, request.user)
        return Response(BatchSerializer(b).data, status=201)


class BatchViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    module_code = "esocial.transmissao"
    serializer_class = BatchSerializer
    action_permissions = {"consultar": "incluir", "eventos": "visualizar"}
    filterset_fields = ["status", "group"]

    queryset = EsocialBatch.objects.select_related("created_by")

    @action(detail=True, methods=["post"])
    def consultar(self, request, pk=None):
        from . import transmission as tx

        return Response(BatchSerializer(tx.query(self.get_object(), request.user)).data)

    @action(detail=True, methods=["get"])
    def eventos(self, request, pk=None):
        return Response(EventSerializer(self.get_object().events.all(), many=True).data)
