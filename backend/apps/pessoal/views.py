"""
Folha de Ativos.
ativos/vencimentos/   tabela de vencimentos (POST cria nova vigência; o valor anterior é encerrado, nunca apagado)
ativos/rubricas/      rubricas (sugestão inicial criada no primeiro acesso)
ativos/lancamentos/   lançamentos por vínculo (?vinculo= &search=)
ativos/folhas/        folhas por órgão (POST {orgao, ano, mes}); calcular/ conferir/ fechar/ reabrir/ excluir/;
                      contracheques/ (?search=), contracheques/<id>/ ; ativos/vinculos/ (busca de vínculos do órgão)
"""
from datetime import date

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.permissions import has_perm
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import format_cpf, only_digits
from apps.core.views import InstitutionScopedMixin

from . import services
from .models import ActiveEntry, ActivePayslip, ActiveRubric, ActiveRun, SalaryScale


def _need(request, perm, what):
    if not has_perm(request, perm):
        raise PermissionDenied(f"Seu perfil não tem permissão para {what}.")


def _date(v, field):
    try:
        s = str(v)
        return date.fromisoformat(s[:10]) if len(s) >= 10 else date.fromisoformat(f"{s[:7]}-01")
    except (TypeError, ValueError):
        raise serializers.ValidationError({field: "Data inválida."})


# ------------------------------------------------------------------ tabela de vencimentos
class ScaleSerializer(serializers.ModelSerializer):
    position_name = serializers.CharField(source="position.name", read_only=True)

    class Meta:
        model = SalaryScale
        fields = ["id", "position", "position_name", "level", "amount", "valid_from", "valid_to", "legal_basis"]
        read_only_fields = ["valid_to"]


class ScaleViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    module_code = "ativos.vencimentos"
    serializer_class = ScaleSerializer
    queryset = SalaryScale.objects.select_related("position")

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("vigentes") == "1":
            qs = qs.filter(valid_to__isnull=True)
        if p.get("cargo"):
            qs = qs.filter(position=p["cargo"])
        if p.get("search"):
            qs = qs.filter(position__name__icontains=p["search"])
        return qs

    def create(self, request, *args, **kwargs):
        from apps.cadastros.models import Position

        d, inst = request.data, self.get_institution()
        pos = Position.objects.filter(institution=inst, pk=d.get("position")).first()
        if pos is None:
            raise serializers.ValidationError({"position": "Escolha o cargo."})
        s = services.new_scale(inst, position=pos, level=d.get("level") or "", amount=d.get("amount"),
                               valid_from=_date(d.get("valid_from"), "valid_from"), legal_basis=d.get("legal_basis") or "")
        return Response(ScaleSerializer(s).data, status=201)


# ------------------------------------------------------------------ rubricas
class RubricSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    calc_display = serializers.CharField(source="get_calc_display", read_only=True)

    class Meta:
        model = ActiveRubric
        exclude = ["institution", "updated_by", "created_by"]


class RubricViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                    viewsets.GenericViewSet):
    module_code = "ativos.rubricas"
    serializer_class = RubricSerializer
    queryset = ActiveRubric.objects.all()
    pagination_class = None

    def get_queryset(self):
        services.ensure_default_rubrics(self.get_institution())
        qs = super().get_queryset()
        if self.request.query_params.get("lancamento") == "1":
            qs = qs.filter(calc="LANCAMENTO", active=True)
        return qs

    def perform_create(self, serializer):
        r = ActiveRubric(institution=self.get_institution(), **serializer.validated_data)
        services.validate_rubric(r)
        r.save()
        serializer.instance = r

    def perform_update(self, serializer):
        if "calc" in serializer.validated_data and serializer.instance.calc != serializer.validated_data["calc"] \
                and serializer.instance.entries.exists():
            raise BusinessRuleError("A forma de cálculo não pode mudar: a rubrica já tem lançamentos.")
        r = serializer.save()
        services.validate_rubric(r)


# ------------------------------------------------------------------ lançamentos
class EntrySerializer(serializers.ModelSerializer):
    rubric_label = serializers.CharField(source="rubric.__str__", read_only=True)
    rubric_kind = serializers.CharField(source="rubric.kind", read_only=True)
    person_name = serializers.CharField(source="link.person.name", read_only=True)
    registration = serializers.CharField(source="link.registration", read_only=True)
    organ_name = serializers.CharField(source="link.organ.name", read_only=True)

    class Meta:
        model = ActiveEntry
        exclude = ["institution", "updated_by", "created_by"]
        read_only_fields = ["paid_installments"]


class EntryViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                   viewsets.GenericViewSet):
    module_code = "ativos.lancamentos"
    serializer_class = EntrySerializer
    queryset = ActiveEntry.objects.select_related("rubric", "link__person", "link__organ")

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("vinculo"):
            qs = qs.filter(link=p["vinculo"])
        if p.get("orgao"):
            qs = qs.filter(link__organ=p["orgao"])
        if p.get("ativos") == "1":
            qs = qs.filter(active=True)
        term = (p.get("search") or "").strip()
        if term:
            cond = Q(link__person__name__icontains=term) | Q(link__registration=term) | Q(rubric__code=term)
            if len(only_digits(term)) >= 3:
                cond |= Q(link__person__cpf__startswith=only_digits(term))
            qs = qs.filter(cond)
        return qs

    def _check(self, e):
        if e.link.institution_id != self.get_institution().pk or e.rubric.institution_id != self.get_institution().pk:
            raise BusinessRuleError("Vínculo ou rubrica de outra instituição.")
        services.validate_entry(e)

    def perform_create(self, serializer):
        e = ActiveEntry(institution=self.get_institution(), **serializer.validated_data)
        self._check(e)
        e.save()
        serializer.instance = e

    def perform_update(self, serializer):
        e = serializer.save()
        self._check(e)
        e.save()


# ------------------------------------------------------------------ folhas e contracheques
class RunSerializer(serializers.ModelSerializer):
    organ_name = serializers.CharField(source="organ.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    checked_by_name = serializers.CharField(source="checked_by.full_name", read_only=True, default="")
    closed_by_name = serializers.CharField(source="closed_by.full_name", read_only=True, default="")

    class Meta:
        model = ActiveRun
        exclude = ["institution", "updated_by", "created_by", "close_effects"]


class PayslipListSerializer(serializers.ModelSerializer):
    person_name = serializers.CharField(source="person.name", read_only=True)
    person_cpf = serializers.SerializerMethodField()

    class Meta:
        model = ActivePayslip
        fields = ["id", "person_name", "person_cpf", "registration", "position_name", "segment", "days", "gross",
                  "discounts", "net", "rpps_base", "employer_contribution", "warnings"]

    def get_person_cpf(self, o):
        return format_cpf(o.person.cpf)


class PayslipSerializer(PayslipListSerializer):
    items = serializers.SerializerMethodField()
    run = RunSerializer(read_only=True)

    class Meta(PayslipListSerializer.Meta):
        fields = PayslipListSerializer.Meta.fields + ["ir_base", "bank", "memory", "items", "run"]

    def get_items(self, o):
        return [{"code": i.code, "name": i.name, "kind": i.kind, "reference": i.reference, "amount": str(i.amount)}
                for i in o.items.all()]


class RunViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    module_code = "ativos.folha"
    serializer_class = RunSerializer
    queryset = ActiveRun.objects.select_related("organ", "checked_by", "closed_by")
    action_permissions = {"create": "incluir", "calcular": "calcular", "conferir": "aprovar", "fechar": "fechar",
                          "reabrir": "reabrir", "excluir": "excluir", "contracheques": "visualizar",
                          "contracheque": "visualizar", "orgaos": "visualizar"}

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("orgao"):
            qs = qs.filter(organ=p["orgao"])
        if p.get("situacao"):
            qs = qs.filter(status=p["situacao"])
        if p.get("ano"):
            qs = qs.filter(year=p["ano"])
        return qs

    def create(self, request, *args, **kwargs):
        from apps.cadastros.models import Organ

        inst, d = self.get_institution(), request.data
        organ = Organ.objects.filter(institution=inst, pk=d.get("orgao")).first()
        if organ is None:
            raise serializers.ValidationError({"orgao": "Escolha o órgão."})
        try:
            year, month = int(d.get("ano")), int(d.get("mes"))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"mes": "Informe mês e ano."})
        return Response(RunSerializer(services.open_run(inst, organ=organ, year=year, month=month)).data, status=201)

    @action(detail=True, methods=["post"])
    def calcular(self, request, pk=None):
        return Response(RunSerializer(services.calculate(self.get_object())).data)

    @action(detail=True, methods=["post"])
    def conferir(self, request, pk=None):
        return Response(RunSerializer(services.check(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def fechar(self, request, pk=None):
        return Response(RunSerializer(services.close(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def reabrir(self, request, pk=None):
        return Response(RunSerializer(services.reopen(self.get_object(), request.data.get("justification", ""))).data)

    @action(detail=True, methods=["post"])
    def excluir(self, request, pk=None):
        services.delete_run(self.get_object(), request.data.get("justification", ""))
        return Response(status=204)

    @action(detail=True, methods=["get"])
    def contracheques(self, request, pk=None):
        run = self.get_object()
        qs = run.payslips.select_related("person")
        term = (request.query_params.get("search") or "").strip()
        if term:
            cond = Q(person__name__icontains=term) | Q(registration=term)
            if len(only_digits(term)) >= 3:
                cond |= Q(person__cpf__startswith=only_digits(term))
            qs = qs.filter(cond)
        if request.query_params.get("avisos") == "1":
            qs = qs.exclude(warnings=[])
        page = self.paginate_queryset(qs.order_by("person__name"))
        return self.get_paginated_response(PayslipListSerializer(page, many=True).data)

    @action(detail=True, methods=["get"], url_path=r"contracheques/(?P<slip>[0-9a-f-]+)")
    def contracheque(self, request, pk=None, slip=None):
        s = self.get_object().payslips.select_related("person", "run__organ").filter(pk=slip).first()
        if s is None:
            raise BusinessRuleError("Contracheque não encontrado.")
        return Response(PayslipSerializer(s).data)

    @action(detail=False, methods=["get"])
    def orgaos(self, request):
        from apps.cadastros.models import Organ
        from apps.employment.models import EmploymentLink

        inst = self.get_institution()
        counts = {r["organ"]: r["n"] for r in EmploymentLink.objects.filter(institution=inst, status="ATIVO")
                  .values("organ").order_by().annotate(n=Count("id"))}
        return Response([{"id": str(o.pk), "nome": o.name, "servidores_ativos": counts.get(o.pk, 0)}
                         for o in Organ.objects.filter(institution=inst).order_by("name")])


class FinancialRecordViewSet(InstitutionScopedMixin, viewsets.GenericViewSet):
    """
    Ficha financeira e controle da contribuição do servidor (`pessoal/ficha.py`).
    GET  ativos/ficha-financeira/modelo/                    tabela padrão (Excel)
    POST ativos/ficha-financeira/importar/                  multipart file [+ pessoa] [+ confirmar=1]
    GET  ativos/ficha-financeira/rubricas/?pessoa=          rubricas importadas e classificação
    POST ativos/ficha-financeira/classificar/               {codigo, classificacao, pessoa?}
    GET  ativos/ficha-financeira/<pessoa>/?ano=&matricula=  ficha do ano
    GET  ativos/ficha-financeira/<pessoa>/excel/?ano=       ficha em Excel
    GET  ativos/ficha-financeira/<pessoa>/contribuicoes/    descontado × devido × repasse por competência
    POST ativos/ficha-financeira/<pessoa>/historico/        bases → salários de contribuição
    """

    module_code = "ativos.ficha_financeira"
    action_permissions = {"modelo": "visualizar", "importar": "incluir", "rubricas": "visualizar",
                          "classificar": "incluir", "retrieve": "visualizar", "excel": "exportar",
                          "contribuicoes": "visualizar", "historico": "incluir", "lancar": "incluir"}

    def get_queryset(self):
        from apps.people.models import Person

        return Person.objects.filter(institution=self.get_institution())

    def _person_param(self, request, key="pessoa"):
        pid = request.data.get(key) if request.method == "POST" else request.query_params.get(key)
        if not pid:
            return None
        person = self.get_queryset().filter(pk=pid).first()
        if person is None:
            raise BusinessRuleError("Servidor não encontrado.")
        return person

    @action(detail=False, methods=["get"])
    def modelo(self, request):
        from django.http import HttpResponse

        from .ficha import template_xlsx

        resp = HttpResponse(template_xlsx(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = 'attachment; filename="SIST_tabela_padrao_ficha_financeira.xlsx"'
        return resp

    @action(detail=False, methods=["post"])
    def importar(self, request):
        from .ficha import import_lines

        upload = request.FILES.get("file")
        if upload is None:
            raise BusinessRuleError("Selecione o arquivo da ficha financeira.")
        if upload.size > 30 * 1024 * 1024:
            raise BusinessRuleError("Arquivo maior que 30 MB.")
        return Response(import_lines(self.get_institution(), upload.read(), upload.name,
                                     person=self._person_param(request),
                                     apply=str(request.data.get("confirmar")) in ("1", "true")))

    @action(detail=False, methods=["get"])
    def rubricas(self, request):
        from .ficha import rubrics

        return Response(rubrics(self.get_institution(), self._person_param(request)))

    @action(detail=False, methods=["post"])
    def classificar(self, request):
        from .ficha import reclassify

        code = str(request.data.get("codigo") or "").strip()
        if not code:
            raise BusinessRuleError("Informe o código da rubrica.")
        n = reclassify(self.get_institution(), code, str(request.data.get("classificacao") or ""),
                       self._person_param(request))
        return Response({"linhas": n})

    def retrieve(self, request, pk=None):
        from .ficha import build

        person = self.get_object()
        year = int(request.query_params.get("ano") or timezone.localdate().year)
        return Response(build(person, year, request.query_params.get("matricula") or None))

    @action(detail=True, methods=["get"])
    def excel(self, request, pk=None):
        from django.http import HttpResponse

        from apps.audit.services import log_event

        from .ficha import export_xlsx

        person = self.get_object()
        year = int(request.query_params.get("ano") or timezone.localdate().year)
        log_event("EXPORT", module="ativos.ficha_financeira", obj=person, object_repr=f"Ficha financeira {year} — {person.name}")
        resp = HttpResponse(export_xlsx(person, year, request.query_params.get("matricula") or None),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="ficha_financeira_{year}_{person.cpf}.xlsx"'
        return resp

    @action(detail=True, methods=["get"])
    def contribuicoes(self, request, pk=None):
        from .ficha import contributions

        ano = request.query_params.get("ano")
        return Response(contributions(self.get_object(), int(ano) if ano else None))

    @action(detail=True, methods=["post"])
    def historico(self, request, pk=None):
        from .ficha import to_history

        if not has_perm(request, "previdenciaria.historico_contributivo:incluir"):
            raise PermissionDenied("Seu perfil não pode incluir salários de contribuição.")
        return Response(to_history(self.get_object()))

    @action(detail=True, methods=["post"])
    def lancar(self, request, pk=None):
        """{competencia: MM/AAAA, vinculo?, base, aliquota? (%), descontado?, tipo_folha?, historico?: bool}"""
        from decimal import Decimal, InvalidOperation

        from apps.employment.models import EmploymentLink

        from .ficha import _comp, add_manual

        person = self.get_object()

        def dec(key):
            v = request.data.get(key)
            if v in (None, ""):
                return None
            try:
                return Decimal(str(v).replace(".", "").replace(",", ".") if "," in str(v) else str(v))
            except InvalidOperation:
                raise BusinessRuleError(f"Valor inválido em {key}.")

        try:
            comp = _comp(request.data.get("competencia"))
        except ValueError as exc:
            raise BusinessRuleError(str(exc))
        link = None
        if request.data.get("vinculo"):
            link = EmploymentLink.objects.filter(person=person, pk=request.data["vinculo"]).first()
            if link is None:
                raise BusinessRuleError("Vínculo inválido.")
        rate = dec("aliquota")
        if rate is not None:
            if not Decimal("0") < rate <= Decimal("50"):
                raise BusinessRuleError("Alíquota em percentual (ex.: 11 ou 14).")
            rate = rate / 100
        hist = request.data.get("historico", True) not in (False, "false", "0", 0)
        if hist and not has_perm(request, "previdenciaria.historico_contributivo:incluir"):
            hist = False
        return Response(add_manual(person, competence=comp, link=link, base=dec("base"), rate=rate,
                                   withheld=dec("descontado"), kind=str(request.data.get("tipo_folha") or "MENSAL"),
                                   to_history_too=hist), status=201)
