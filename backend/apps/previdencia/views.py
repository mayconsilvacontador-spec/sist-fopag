from datetime import date

from django.http import HttpResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.core.views import InstitutionScopedMixin, get_justification
from apps.people.models import Person

from . import services
from .models import Averbacao, ContributionSalary, CorrectionFactor, Ctc, CtcStatus, LegalNorm, RetirementRule
from .serializers import AverbacaoSerializer, ContributionSalarySerializer, CtcSerializer, RetirementRuleSerializer


def _person(request, pk) -> Person:
    person = Person.objects.filter(institution=request.institution, pk=pk).first()
    if person is None:
        raise serializers.ValidationError({"person": "Pessoa não encontrada."})
    return person


def _date_param(request, name="data") -> date | None:
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise serializers.ValidationError({name: "Data inválida (AAAA-MM-DD)."})


class TimeView(APIView):
    """GET previdencia/tempo/<pessoa>/?data= — apuração do tempo de contribuição."""

    module_code = "previdenciaria.tempo_contribuicao"

    def get(self, request, pk):
        return Response(services.time_report(_person(request, pk), _date_param(request)))


class SimulationView(APIView):
    """GET previdencia/simulacao/<pessoa>/?data= — enquadramento em todas as regras e abono de permanência."""

    module_code = "previdenciaria.simulacao"

    def get(self, request, pk):
        person = _person(request, pk)
        result = services.simulate(person, _date_param(request))
        log_event("CALCULATE", module="previdenciaria.simulacao", obj=person,
                  object_repr=f"Simulação de aposentadoria — {person.name or person.cpf}")
        return Response(result)


class AverbacaoViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                       mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Averbações (?person=). Sem exclusão: inativar."""

    module_code = "previdenciaria.averbacoes"
    serializer_class = AverbacaoSerializer
    queryset = Averbacao.objects.all()
    filterset_fields = ["person", "nature", "active"]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        return qs if self.action != "list" or self.request.query_params.get("person") else qs.none()


class ContributionSalaryViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.CreateModelMixin,
                                mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """
    Histórico contributivo (?person=). Exclusão permitida para corrigir digitação (auditada).
    POST import/ (multipart: person, file) importa CSV; GET salcontr/ gera o arquivo da Deliberação 260.
    """

    module_code = "previdenciaria.historico_contributivo"
    serializer_class = ContributionSalarySerializer
    queryset = ContributionSalary.objects.all()
    filterset_fields = ["person", "regime"]
    pagination_class = None
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {"import_csv": "incluir", "import_batch": "incluir", "salcontr": "exportar"}

    def get_queryset(self):
        qs = super().get_queryset()
        return qs if self.action != "list" or self.request.query_params.get("person") else qs.none()

    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        person = _person(request, request.data.get("person"))
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "Selecione o arquivo CSV."})
        result = services.import_salaries(person, upload.read())
        log_event("CREATE", module="previdenciaria.historico_contributivo", obj=person,
                  object_repr="Importação de salários de contribuição", extra=result | {"erros": len(result["erros"])})
        return Response(result)

    @action(detail=False, methods=["post"], url_path="import-lote")
    def import_batch(self, request):
        """Lote de vários segurados: CSV cpf;competencia;valor;regime;vinculo."""
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "Selecione o arquivo CSV."})
        if upload.size > 50 * 1024 * 1024:
            raise serializers.ValidationError({"file": "Arquivo muito grande (máx. 50 MB)."})
        result = services.import_salaries_batch(self.get_institution(), upload.read())
        log_event("CREATE", module="previdenciaria.historico_contributivo",
                  object_repr=f"Importação em lote de salários ({upload.name})",
                  extra={k: v for k, v in result.items() if k != "erros"} | {"erros": len(result["erros"])})
        return Response(result)

    @action(detail=False, methods=["get"])
    def salcontr(self, request):
        p = request.query_params
        person = _person(request, p.get("person"))
        txt = services.salcontr_txt(person, unidade_gestora=p.get("ug", ""), orgao=p.get("orgao", ""),
                                    matricula=p.get("matricula", ""), processo=p.get("processo", ""),
                                    tipo_ato=int(p.get("tipo_ato") or 1))
        log_event("EXPORT", module="previdenciaria.historico_contributivo", obj=person,
                  object_repr="SalContr.txt (Deliberação TCE-RJ 260)")
        resp = HttpResponse(txt.encode("latin-1", errors="replace"), content_type="text/plain; charset=latin-1")
        resp["Content-Disposition"] = 'attachment; filename="SalContr.txt"'
        return resp


class CorrectionFactorView(APIView):
    """GET: tabelas cadastradas; POST (multipart: table_month AAAA-MM, file) importa uma tabela de fatores."""

    module_code = "previdenciaria.historico_contributivo"
    parser_classes = [MultiPartParser, FormParser]
    action_permissions = {"POST": "incluir"}

    def get(self, request):
        from django.db.models import Count

        rows = (CorrectionFactor.objects.filter(institution=request.institution).values("table_month")
                .annotate(n=Count("id")).order_by("-table_month"))
        return Response([{"mes": r["table_month"].strftime("%m/%Y"), "competencias": r["n"]} for r in rows])

    def post(self, request):
        raw = (request.data.get("table_month") or "").strip()
        try:
            table = date.fromisoformat(raw + "-01" if len(raw) == 7 else raw)
        except ValueError:
            raise serializers.ValidationError({"table_month": "Informe o mês da tabela (AAAA-MM)."})
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "Selecione o arquivo CSV."})
        return Response(services.import_factors(request.institution, table, upload.read()))


class RetirementRuleViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Regras versionadas. Alterações exigem justificativa e ficam na auditoria."""

    module_code = "previdenciaria.regras"
    serializer_class = RetirementRuleSerializer
    queryset = RetirementRule.objects.all()
    pagination_class = None

    def perform_update(self, serializer):
        just = get_justification(self.request)
        if len(just) < 10:
            raise BusinessRuleError("Informe a justificativa da alteração da regra (mínimo de 10 caracteres).")
        old = RetirementRuleSerializer(serializer.instance).data
        rule = serializer.save()
        log_event("UPDATE", module="previdenciaria.regras", obj=rule, old={"params": old["params"]},
                  new={"params": rule.params}, justification=just)


class CtcViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """CTC: POST emite (person, destination, purpose, period_start, period_end, process); POST {id}/cancel/."""

    module_code = "previdenciaria.ctc"
    serializer_class = CtcSerializer
    queryset = Ctc.objects.select_related("person", "created_by", "process").all()
    filterset_fields = ["person", "status", "year"]
    action_permissions = {"cancel": "excluir"}

    def create(self, request, *args, **kwargs):
        person = _person(request, request.data.get("person"))
        try:
            start = date.fromisoformat(request.data.get("period_start", ""))
            end = date.fromisoformat(request.data.get("period_end", ""))
        except ValueError:
            raise serializers.ValidationError({"period_start": "Informe o período certificado."})
        destination = (request.data.get("destination") or "").strip()
        if not destination:
            raise serializers.ValidationError({"destination": "Informe o órgão/regime de destino."})
        process = None
        if request.data.get("process"):
            from apps.protocolo.models import Process
            process = Process.objects.filter(institution=request.institution, pk=request.data["process"]).first()
        ctc = services.issue_ctc(person, destination=destination,
                                 purpose=(request.data.get("purpose") or "Averbação / contagem recíproca").strip(),
                                 period_start=start, period_end=end, process=process,
                                 issuer_name=request.user.full_name)
        log_event("CREATE", module="previdenciaria.ctc", obj=ctc, object_repr=f"CTC {ctc.code} — {person.name}",
                  extra={"sha256": ctc.sha256})
        return Response(self.get_serializer(ctc).data, status=201)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ctc = self.get_object()
        if ctc.status != CtcStatus.EMITIDA:
            raise BusinessRuleError("A CTC já está cancelada.")
        just = get_justification(request)
        if len(just) < 10:
            raise BusinessRuleError("Informe o motivo do cancelamento (mínimo de 10 caracteres).")
        ctc.status, ctc.cancel_reason = CtcStatus.CANCELADA, just
        ctc.save()
        log_event("CANCEL", module="previdenciaria.ctc", obj=ctc, justification=just)
        return Response(self.get_serializer(ctc).data)


class LegalNormViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Legislação do RPPS. POST cria (multipart: campos + file PDF); POST {id}/salvar/ altera; POST {id}/inativar/;
    GET {id}/arquivo/. Sem exclusão (regras e concessões citam a norma)."""

    module_code = "previdenciaria.regras"
    queryset = LegalNorm.objects.all()
    pagination_class = None
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    action_permissions = {"create": "incluir", "salvar": "editar", "inativar": "editar", "arquivo": "visualizar"}

    def get_serializer_class(self):
        from .serializers import LegalNormSerializer

        return LegalNormSerializer

    @staticmethod
    def _data(request):
        d = request.data
        subjects = d.getlist("subjects") if hasattr(d, "getlist") else d.get("subjects") or []
        if len(subjects) == 1 and "," in subjects[0]:
            subjects = subjects[0].split(",")
        return {**{k: d.get(k) for k in ("kind", "number", "date", "publication_date", "valid_from", "valid_to",
                                         "summary", "url")}, "subjects": subjects}

    def create(self, request, *args, **kwargs):
        from .legislacao import save_norm
        from .serializers import LegalNormSerializer

        n = save_norm(self.get_institution(), self._data(request), request.FILES.get("file"))
        return Response(LegalNormSerializer(n).data, status=201)

    @action(detail=True, methods=["post"])
    def salvar(self, request, pk=None):
        from .legislacao import save_norm
        from .serializers import LegalNormSerializer

        n = save_norm(self.get_institution(), self._data(request), request.FILES.get("file"), norm=self.get_object())
        return Response(LegalNormSerializer(n).data)

    @action(detail=True, methods=["post"])
    def inativar(self, request, pk=None):
        from .serializers import LegalNormSerializer

        n = self.get_object()
        n.active = not n.active
        n.save(update_fields=["active", "updated_at"])
        log_event("UPDATE", module="previdenciaria.regras", obj=n,
                  object_repr=f"Legislação do RPPS — {n.citation} {'reativada' if n.active else 'inativada'}")
        return Response(LegalNormSerializer(n).data)

    @action(detail=True, methods=["get"])
    def arquivo(self, request, pk=None):
        from django.http import FileResponse, Http404

        n = self.get_object()
        if not n.file:
            raise Http404
        resp = FileResponse(n.file.open("rb"), content_type="application/pdf")
        resp["Content-Disposition"] = "inline; filename=norma.pdf"
        return resp


class RulePackagesView(InstitutionScopedMixin, APIView):
    """GET pacotes-modelo e situação; POST {pacote, reforma (AAAA-MM-DD), norma, justificativa} aplica o pacote."""

    module_code = "previdenciaria.regras"
    action_permissions = {"GET": "visualizar", "POST": "editar"}

    def get(self, request):
        from .legislacao import packages_info

        return Response(packages_info(self.get_institution()))

    def post(self, request):
        from .legislacao import apply_package

        inst, d = self.get_institution(), request.data
        reform = None
        if d.get("reforma"):
            try:
                reform = date.fromisoformat(str(d["reforma"])[:10])
            except ValueError:
                raise BusinessRuleError("Data da reforma inválida.")
        norm = LegalNorm.objects.filter(institution=inst, pk=d.get("norma")).first() if d.get("norma") else None
        return Response(apply_package(inst, str(d.get("pacote") or ""), reform=reform, norm=norm,
                                      justification=str(d.get("justificativa") or ""), user=request.user))
