from datetime import date

from django.db.models import Q
from django.http import HttpResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import has_perm
from apps.core.validators import only_digits
from apps.core.views import InstitutionScopedMixin

from . import checklist, fatima, services, workflow
from .models import (
    Benefit, BenefitEventKind, BenefitKind, ChecklistSector, ChecklistTemplate, Concession, ConcessionKind,
    DocumentTemplate,
)
from .serializers import (
    BenefitEventSerializer, BenefitSerializer, ChecklistItemSerializer, ChecklistTemplateSerializer,
    ConcessionListSerializer, ConcessionSerializer, DocumentSerializer, StepSerializer, TemplateSerializer,
)


def _date(value, name):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise serializers.ValidationError({name: "Data inválida."})


def _module(kind: str) -> str:
    return {"APOSENTADORIA": "concessao.aposentadoria", "PENSAO": "concessao.pensao",
            "REVISAO": "concessao.revisao"}.get(kind, "concessao.processos")


def _check(request, kind: str, act: str):
    if not has_perm(request, f"{_module(kind)}:{act}"):
        raise PermissionDenied("Você não possui permissão para esta etapa da concessão.")


def _need(request, perm: str, who: str):
    if not has_perm(request, perm):
        raise PermissionDenied(f"Ato reservado a {who}. Seu perfil não tem essa permissão.")


def _cadastro(person) -> dict:
    """Dados atuais do cadastro para conferência ao anexar comprovante de residência / identidade."""
    from apps.people.models import Address

    a = Address.objects.filter(person=person, valid_to__isnull=True).first()
    return {
        "nome": person.name,
        "endereco": {"cep": a.cep, "street": a.street, "number": a.number, "complement": a.complement,
                     "district": a.district, "city": a.city, "uf": a.uf} if a else None,
        "identidade": {"rg_number": person.rg_number, "rg_issuer": person.rg_issuer, "rg_uf": person.rg_uf,
                       "rg_date": person.rg_date.isoformat() if person.rg_date else ""},
    }


def _yes(v) -> bool:
    return str(v).lower() in ("true", "1", "sim", "s")


class ConcessionViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """
    Processos de concessão e revisão. POST abre (process, kind, person | benefit).
    Instrução (Benefícios): frame, calculate, parcels, revision, send.
    Decisões (cada uma com permissão própria, segregação de funções e senha): legal, compliance, sign, reject,
    publish, implant, tce-send, tce-judgment, annul. Consulta: steps (trilha), documents, ficha (FATIMA).
    """

    module_code = "concessao.processos"
    queryset = Concession.objects.select_related(
        "person", "process", "rule", "link__position", "link__organ", "approved_by", "revised_benefit__beneficiary",
    ).prefetch_related("parcels", "quotas__dependent")
    filterset_fields = ["kind", "stage", "person"]
    # A permissão real de cada ato é conferida dentro da ação (módulo do tipo de processo ou do setor decisório)
    action_permissions = {a: "visualizar" for a in (
        "frame", "calculate", "parcels", "revision", "send", "legal", "compliance", "sign", "reject", "publish",
        "implant", "tce_send", "tce_judgment", "annul", "steps", "documents", "download", "ficha", "comparativo",
        "suspend", "resume", "withdraw", "checklist", "checklist_attach", "checklist_waive", "checklist_reopen")}
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        return ConcessionListSerializer if self.action == "list" else ConcessionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        term = (self.request.query_params.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(person__name__icontains=term)
            if digits:
                cond |= Q(person__cpf__startswith=digits) | Q(process__number=int(digits[:9]))
            qs = qs.filter(cond)
        etapas = [s for s in (self.request.query_params.get("etapas") or "").split(",") if s]
        if etapas:
            qs = qs.filter(stage__in=etapas)
        return qs

    def create(self, request, *args, **kwargs):
        from apps.employment.models import EmploymentLink
        from apps.people.models import Person
        from apps.protocolo.models import Process

        inst = self.get_institution()
        kind = request.data.get("kind")
        if kind not in ConcessionKind.values:
            raise serializers.ValidationError({"kind": "Tipo inválido."})
        _check(request, kind, "incluir")
        process = Process.objects.filter(institution=inst, pk=request.data.get("process")).first()
        if process is None:
            raise serializers.ValidationError({"process": "Informe o processo do Protocolo."})
        rd = _date(request.data["request_date"], "request_date") if request.data.get("request_date") else None
        if kind == ConcessionKind.REVISAO:
            benefit = Benefit.objects.filter(institution=inst, pk=request.data.get("benefit")).first()
            c = services.open_concession(inst, process=process, kind=kind, person=None, request_date=rd, benefit=benefit)
        else:
            person = Person.objects.filter(institution=inst, pk=request.data.get("person")).first()
            if person is None:
                raise serializers.ValidationError({"person": "Informe a pessoa."})
            link = EmploymentLink.objects.filter(institution=inst, pk=request.data.get("link")).first() \
                if request.data.get("link") else None
            c = services.open_concession(inst, process=process, kind=kind, person=person, link=link, request_date=rd)
        return Response(ConcessionSerializer(c).data, status=201)

    def _ok(self, c):
        return Response(ConcessionSerializer(Concession.objects.get(pk=c.pk)).data)

    # ------------------------------------------------------------ instrução (setor de Benefícios)
    @action(detail=True, methods=["post"])
    def frame(self, request, pk=None):
        from apps.previdencia.models import RetirementRule

        c = self.get_object()
        _check(request, c.kind, "calcular")
        d = request.data
        rule = RetirementRule.objects.filter(institution=c.institution, code=d.get("rule")).first() if d.get("rule") else None
        c = services.frame_retirement(
            c, rule=rule, modality=int(d["modality"]) if d.get("modality") else None,
            validity_date=_date(d.get("validity_date"), "validity_date"),
            validity_class=int(d.get("validity_class") or 1), validity_legal_basis=d.get("validity_legal_basis", ""),
            invalidity_cause=int(d["invalidity_cause"]) if d.get("invalidity_cause") else None, cid=d.get("cid", ""),
            medical_report_date=_date(d["medical_report_date"], "medical_report_date") if d.get("medical_report_date") else None,
            judicial=bool(d.get("judicial")), judicial_process=d.get("judicial_process", ""),
            local_legal_basis=d.get("local_legal_basis", ""), user=request.user,
            base_date_override=_date(d["base_date"], "base_date") if d.get("base_date") else None,
            base_date_reason=d.get("base_date_reason", ""), option_reason=d.get("option_reason", ""),
            option_signed=_yes(d.get("option_signed")))
        return self._ok(c)

    @action(detail=True, methods=["get"])
    def comparativo(self, request, pk=None):
        """Regras cumpridas até a data de validade e o valor de cada uma (benefício mais favorável)."""
        c = self.get_object()
        _check(request, c.kind, "calcular")
        if c.kind != BenefitKind.APOSENTADORIA:
            raise serializers.ValidationError({"detail": "Comparativo de regras é só para aposentadoria."})
        validity = _date(request.query_params.get("validity_date"), "validity_date")
        base = _date(request.query_params["base_date"], "base_date") if request.query_params.get("base_date") else None
        return Response(services.compare_rules(c, validity, base))

    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        c = self.get_object()
        _check(request, c.kind, "calcular")
        if c.kind == BenefitKind.PENSAO and c.stage == "INSTRUCAO":
            c.stage = "ENQUADRADO"  # pensão não tem enquadramento por regra
            c.save(update_fields=["stage"])
        return self._ok(services.calculate(c, user=request.user))

    @action(detail=True, methods=["post"])
    def parcels(self, request, pk=None):
        c = self.get_object()
        _check(request, c.kind, "editar")
        items = request.data.get("parcels")
        if not isinstance(items, list):
            raise serializers.ValidationError({"parcels": "Lista de parcelas inválida."})
        return self._ok(services.update_parcels(c, items, user=request.user))

    @action(detail=True, methods=["post"])
    def revision(self, request, pk=None):
        c = self.get_object()
        _check(request, c.kind, "calcular")
        return self._ok(services.set_revision(c, amount=request.data.get("amount"), reason=request.data.get("reason", ""),
                                              validity_date=_date(request.data.get("validity_date"), "validity_date"),
                                              user=request.user))

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        c = self.get_object()
        _check(request, c.kind, "editar")
        return self._ok(workflow.send_to_legal(c, request.user,
                                               acknowledge_warnings=_yes(request.data.get("acknowledge_warnings")),
                                               password=request.data.get("password", "")))

    # ------------------------------------------------------------ processo digital: checklist por setor
    def _checklist_perm(self, request, c, sector: str):
        """Quem pode anexar: o setor dono do item (Benefícios = editar do tipo; demais = módulo decisório)."""
        perm = {"BENEFICIOS": f"{_module(c.kind)}:editar", "JURIDICO": "concessao.juridico:aprovar",
                "CONTROLE": "concessao.controle_interno:aprovar", "PRESIDENCIA": "concessao.presidencia:aprovar",
                "FOLHA": "concessao.implantacao:aprovar"}[sector]
        _need(request, perm, f"setor {ChecklistSector(sector).label}")

    def _item(self, c, item_id):
        item = c.checklist.filter(pk=item_id).first()
        if item is None:
            raise serializers.ValidationError({"item": "Item do checklist não encontrado."})
        return item

    def _checklist_response(self, c):
        items = checklist.sync(c)
        sector = checklist.current_sector(c)
        return Response({"setor_atual": sector, "itens": ChecklistItemSerializer(items, many=True).data,
                         "pendentes_setor_atual": [i.name for i in checklist.pending(c, sector)] if sector else [],
                         "cadastro": _cadastro(c.person)})

    @action(detail=True, methods=["get"])
    def checklist(self, request, pk=None):
        return self._checklist_response(self.get_object())

    @action(detail=True, methods=["post"], url_path=r"checklist/(?P<item_id>[^/.]+)/attach")
    def checklist_attach(self, request, pk=None, item_id=None):
        c = self.get_object()
        item = self._item(c, item_id)
        self._checklist_perm(request, c, item.sector)
        import json

        raw = request.data.get("dados")
        try:
            data = json.loads(raw) if isinstance(raw, str) and raw else (raw if isinstance(raw, dict) else None)
        except ValueError:
            raise serializers.ValidationError({"dados": "Dados inválidos."})
        checklist.attach(c, item, request.FILES.get("file"), request.user, data)
        return self._checklist_response(c)

    @action(detail=True, methods=["post"], url_path=r"checklist/(?P<item_id>[^/.]+)/waive")
    def checklist_waive(self, request, pk=None, item_id=None):
        c = self.get_object()
        item = self._item(c, item_id)
        self._checklist_perm(request, c, item.sector)
        checklist.waive(c, item, request.data.get("note", ""), request.user)
        return self._checklist_response(c)

    @action(detail=True, methods=["post"], url_path=r"checklist/(?P<item_id>[^/.]+)/reopen")
    def checklist_reopen(self, request, pk=None, item_id=None):
        c = self.get_object()
        item = self._item(c, item_id)
        self._checklist_perm(request, c, item.sector)
        checklist.reopen(c, item, request.user)
        return self._checklist_response(c)

    # ------------------------------------------------------------ sobrestamento e desistência (Benefícios, com senha)
    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        c = self.get_object()
        _check(request, c.kind, "editar")
        d = request.data
        until = _date(d["until"], "until") if d.get("until") else None
        return self._ok(workflow.suspend(c, request.user, reason=d.get("reason", ""), until=until,
                                         password=d.get("password", "")))

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        c = self.get_object()
        _check(request, c.kind, "editar")
        d = request.data
        return self._ok(workflow.resume(c, request.user, text=d.get("text", ""), password=d.get("password", "")))

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        c = self.get_object()
        _check(request, c.kind, "editar")
        d = request.data
        return self._ok(workflow.withdraw(c, request.user, reason=d.get("reason", ""),
                                          request_attached=_yes(d.get("request_attached")),
                                          password=d.get("password", "")))

    # ------------------------------------------------------------ decisões (setores competentes, com senha)
    @action(detail=True, methods=["post"])
    def legal(self, request, pk=None):
        _need(request, "concessao.juridico:aprovar", "Procuradoria Jurídica")
        d = request.data
        return self._ok(workflow.legal_opinion(self.get_object(), request.user, favorable=_yes(d.get("favorable")),
                                               text=d.get("text", ""), password=d.get("password", "")))

    @action(detail=True, methods=["post"])
    def compliance(self, request, pk=None):
        _need(request, "concessao.controle_interno:aprovar", "Controle Interno")
        d = request.data
        return self._ok(workflow.compliance(self.get_object(), request.user, conform=_yes(d.get("conform")),
                                            text=d.get("text", ""), password=d.get("password", "")))

    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        _need(request, "concessao.presidencia:aprovar", "Presidência")
        d = request.data
        return self._ok(workflow.sign(self.get_object(), request.user, nature=d.get("nature") or "PORTARIA",
                                      number=d.get("number") or "", act_date=_date(d.get("act_date"), "act_date"),
                                      password=d.get("password", "")))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        _need(request, "concessao.presidencia:aprovar", "Presidência")
        return self._ok(workflow.reject(self.get_object(), request.user, reason=request.data.get("reason", ""),
                                        password=request.data.get("password", "")))

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        _need(request, "concessao.implantacao:aprovar", "setor de Folha de Pagamento")
        d = request.data
        return self._ok(workflow.publish(self.get_object(), request.user,
                                         publication_date=_date(d.get("publication_date"), "publication_date"),
                                         media=d.get("media", ""), password=d.get("password", "")))

    @action(detail=True, methods=["post"])
    def implant(self, request, pk=None):
        _need(request, "concessao.implantacao:aprovar", "setor de Folha de Pagamento")
        c = self.get_object()
        workflow.implant(c, request.user, password=request.data.get("password", ""))
        return self._ok(c)

    @action(detail=True, methods=["post"], url_path="tce-send")
    def tce_send(self, request, pk=None):
        _need(request, "concessao.tce:editar", "setor de COMPREV/TCE")
        d = request.data
        return self._ok(workflow.tce_send(self.get_object(), request.user, sent_date=_date(d.get("sent_date"), "sent_date"),
                                          reference=d.get("reference", "")))

    @action(detail=True, methods=["post"], url_path="tce-judgment")
    def tce_judgment(self, request, pk=None):
        _need(request, "concessao.tce:editar", "setor de COMPREV/TCE")
        d = request.data
        return self._ok(workflow.tce_judgment(self.get_object(), request.user, result=d.get("result", ""),
                                              result_date=_date(d.get("result_date"), "result_date"),
                                              notes=d.get("notes", "")))

    @action(detail=True, methods=["post"])
    def annul(self, request, pk=None):
        _need(request, "concessao.presidencia:aprovar", "Presidência")
        d = request.data
        return self._ok(workflow.annul(self.get_object(), request.user, number=d.get("number") or "",
                                       act_date=_date(d.get("act_date"), "act_date"), password=d.get("password", "")))

    # ------------------------------------------------------------ consulta
    @action(detail=True, methods=["get"])
    def steps(self, request, pk=None):
        c = self.get_object()
        return Response(StepSerializer(c.steps.select_related("user"), many=True).data)

    @action(detail=True, methods=["get"])
    def documents(self, request, pk=None):
        c = self.get_object()
        return Response(DocumentSerializer(c.documents.select_related("created_by"), many=True).data)

    @action(detail=True, methods=["get"], url_path=r"documents/(?P<doc_id>[^/.]+)/download")
    def download(self, request, pk=None, doc_id=None):
        doc = self.get_object().documents.filter(pk=doc_id).first()
        if doc is None:
            raise serializers.ValidationError("Documento não encontrado.")
        resp = HttpResponse(doc.file.read(),
                            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        resp["Content-Disposition"] = f'attachment; filename="{doc.file_name}"'
        return resp

    @action(detail=True, methods=["get"])
    def ficha(self, request, pk=None):
        return Response(fatima.ficha(self.get_object()))


class ChecklistTemplateViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                               mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Documentos exigidos por tipo de processo e setor (processo digital). Não há exclusão: inativar."""

    module_code = "concessao.modelos"
    serializer_class = ChecklistTemplateSerializer
    queryset = ChecklistTemplate.objects.all()
    filterset_fields = ["concession_kind", "sector", "active"]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        checklist.ensure_default_templates(self.get_institution())
        return super().list(request, *args, **kwargs)


class TemplateViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Modelos de texto das portarias e ofícios (marcadores entre chaves). GET defaults/ = textos padrão."""

    module_code = "concessao.modelos"
    serializer_class = TemplateSerializer
    queryset = DocumentTemplate.objects.all()
    action_permissions = {"defaults": "visualizar"}

    @action(detail=False, methods=["get"])
    def defaults(self, request):
        from .documents import DEFAULT_TEMPLATES

        return Response([{"kind": k, "concession_kind": ck, "title": t, "body": b}
                         for (k, ck), (t, b) in DEFAULT_TEMPLATES.items()])


EVENT_MODULE = {
    BenefitEventKind.SUSPENSAO: "concessao.suspensao", BenefitEventKind.RESTABELECIMENTO: "concessao.suspensao",
    BenefitEventKind.CESSACAO: "concessao.cessacao", BenefitEventKind.REVERSAO: "concessao.reversao",
}


class BenefitViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Benefícios implantados (base da folha). POST {id}/event/ {kind, date, justification, act, password}.
    A revisão de valor NÃO é feita aqui: exige processo próprio (Concessão › Revisão).
    """

    module_code = "folha.beneficiarios"
    serializer_class = BenefitSerializer
    queryset = Benefit.objects.select_related("beneficiary", "instituidor", "payroll_group", "concession__process").all()
    filterset_fields = ["kind", "status", "payroll_group", "beneficiary", "instituidor"]
    action_permissions = {"event": "visualizar", "events": "visualizar", "esocial": "editar"}

    def get_queryset(self):
        qs = super().get_queryset()
        term = (self.request.query_params.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            cond = Q(beneficiary__name__icontains=term) | Q(instituidor__name__icontains=term) | Q(registration__icontains=term)
            if len(digits) >= 3:
                cond |= Q(beneficiary__cpf__startswith=digits)
            qs = qs.filter(cond)
        massa = self.request.query_params.get("massa")
        if massa:
            qs = qs.filter(payroll_group__segment=massa)
        return qs

    @action(detail=True, methods=["post"])
    def esocial(self, request, pk=None):
        """Códigos do eSocial: tipo de benefício (Tabela 25) e motivo do término (Tabela 26)."""
        b = self.get_object()
        tp = only_digits(request.data.get("esocial_tp_beneficio", b.esocial_tp_beneficio))
        mt = only_digits(request.data.get("esocial_mtv_termino", b.esocial_mtv_termino))
        if tp and len(tp) != 4:
            raise serializers.ValidationError({"esocial_tp_beneficio": "Informe os 4 dígitos da Tabela 25."})
        if mt and len(mt) != 2:
            raise serializers.ValidationError({"esocial_mtv_termino": "Informe os 2 dígitos da Tabela 26."})
        b.esocial_tp_beneficio, b.esocial_mtv_termino = tp, mt
        b.save(update_fields=["esocial_tp_beneficio", "esocial_mtv_termino", "updated_at"])  # auditado
        return Response(BenefitSerializer(b).data)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        b = self.get_object()
        return Response(BenefitEventSerializer(b.events.select_related("created_by"), many=True).data)

    @action(detail=True, methods=["post"])
    def event(self, request, pk=None):
        from apps.core.exceptions import BusinessRuleError

        b = self.get_object()
        kind = request.data.get("kind")
        if kind == BenefitEventKind.REVISAO:
            raise BusinessRuleError("A revisão de valor exige processo próprio em Concessão › Revisão (parecer jurídico, "
                                    "portaria assinada pela Presidência e publicação).")
        if kind not in EVENT_MODULE:
            raise serializers.ValidationError({"kind": "Operação inválida."})
        if not has_perm(request, f"{EVENT_MODULE[kind]}:incluir"):
            raise PermissionDenied("Você não possui permissão para esta operação.")
        workflow.confirm_password(request.user, request.data.get("password", ""))
        b = services.event(b, kind, _date(request.data.get("date"), "date"), request.data.get("justification", ""),
                           act=request.data.get("act", ""))
        return Response(BenefitSerializer(b).data)


class LegacyBenefitViewSet(InstitutionScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Benefícios importados (base SPREV) — já concedidos no sistema anterior — aguardando implantação.
    POST {id}/implant/ ou implant-all/ {password}.
    """

    module_code = "folha.beneficiarios"
    action_permissions = {"implant": "incluir", "implant_all": "incluir"}

    def get_queryset(self):
        from apps.people.models import LegacyBenefit

        qs = LegacyBenefit.objects.filter(institution=self.get_institution()).select_related("beneficiary", "instituidor")
        pending = self.request.query_params.get("pendentes", "1") == "1"
        return qs.filter(implanted=False) if pending else qs

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        rows = [{"id": str(x.pk), "kind": x.kind, "beneficiary_name": x.beneficiary.name,
                 "beneficiary_cpf": x.beneficiary.cpf, "instituidor_name": x.instituidor.name if x.instituidor else "",
                 "segment": x.segment, "start_date": x.start_date, "amount": str(x.amount) if x.amount else None,
                 "registration": x.registration, "implanted": x.implanted} for x in page]
        return self.get_paginated_response(rows)

    @action(detail=True, methods=["post"])
    def implant(self, request, pk=None):
        legacy = self.get_queryset().filter(pk=pk).first()
        if legacy is None:
            raise serializers.ValidationError("Benefício importado não encontrado ou já implantado.")
        workflow.confirm_password(request.user, request.data.get("password", ""))
        return Response(BenefitSerializer(services.implant_legacy(legacy)).data)

    @action(detail=False, methods=["post"], url_path="implant-all")
    def implant_all(self, request):
        from apps.core.exceptions import BusinessRuleError

        workflow.confirm_password(request.user, request.data.get("password", ""))
        ok, errors = 0, []
        for legacy in self.get_queryset():
            try:
                services.implant_legacy(legacy)
                ok += 1
            except BusinessRuleError as exc:
                errors.append({"beneficiario": legacy.beneficiary.name or legacy.beneficiary.cpf, "erro": exc.message})
        return Response({"implantados": ok, "erros": errors})
