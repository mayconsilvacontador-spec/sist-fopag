"""
Rotas do Portal do Segurado.

- /portal/auth/token/ ............ login por CPF + senha (somente usuários do portal)
- /portal/me/ e demais /portal/... dados do PRÓPRIO segurado (pessoa vinculada ao acesso)
- /portal-admin/... ............... gestão de acessos e solicitações pela equipe do RPPS (módulo 'portal')
"""
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.validators import format_cpf, only_digits
from apps.core.views import InstitutionScopedMixin, get_justification

from . import services
from .models import PortalAccess, PortalRequest, RequestKind


class IsPortalUser(BasePermission):
    message = "Acesso exclusivo do Portal do Segurado."

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and getattr(u, "is_portal", False)):
            return False
        acc = PortalAccess.objects.filter(user=u, active=True).select_related("person", "institution").first()
        if acc is None:
            return False
        if u.must_change_password and not getattr(view, "allow_pending_password", False):
            self.message = {"detail": "Troque a senha provisória antes de continuar.", "code": "troca_senha_obrigatoria"}
            return False
        request.portal = acc
        return True


class PortalView(APIView):
    permission_classes = [IsAuthenticated, IsPortalUser]
    portal_allowed = True

    @property
    def person(self):
        return self.request.portal.person

    @property
    def institution(self):
        return self.request.portal.institution


# ------------------------------------------------------------------ autenticação
class PortalLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        cpf = only_digits(request.data.get("cpf") or request.data.get("username") or "")
        password = request.data.get("password") or ""
        if len(cpf) != 11 or not password:
            return Response({"detail": "Informe CPF e senha."}, status=status.HTTP_400_BAD_REQUEST)
        acc, error = services.authenticate(cpf, password)
        if acc is None:
            return Response({"detail": error, "code": "credenciais_invalidas"}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(acc.user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh),
                         "must_change_password": acc.user.must_change_password,
                         "institution_id": str(acc.institution_id), "portal": True})


# ------------------------------------------------------------------ dados do segurado
def _life_proofs(person):
    from apps.provadevida.services import portal_pending

    return portal_pending(person)


class MeView(PortalView):
    allow_pending_password = True

    def get(self, request):
        from apps.people.models import Address, BankAccount, Dependency

        p = self.person
        today = timezone.localdate()
        addr = Address.objects.filter(person=p, valid_from__lte=today).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=today)).order_by("-valid_from").first()
        acc = BankAccount.objects.filter(person=p, valid_from__lte=today).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=today)).select_related("bank").order_by("-valid_from").first()
        deps = Dependency.objects.filter(holder=p).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)) \
            .select_related("dependent")
        inst = self.institution
        return Response({
            "must_change_password": request.user.must_change_password,
            "instituicao": {"nome": inst.name, "sigla": inst.short_name, "telefone": inst.phone, "email": inst.email,
                            "site": inst.website},
            "pessoa": {"nome": p.name, "nome_social": p.social_name, "cpf": format_cpf(p.cpf), "nascimento": p.birth_date,
                       "email": p.email, "telefone": p.phone, "celular": p.mobile},
            "endereco": {"logradouro": addr.street, "numero": addr.number, "complemento": addr.complement,
                         "bairro": addr.district, "cidade": addr.city, "uf": addr.uf, "cep": addr.cep} if addr else None,
            # Conta mascarada: o portal mostra só os 4 últimos dígitos
            "conta": {"banco": f"{acc.bank.code} - {acc.bank.name}", "agencia": acc.branch,
                      "conta": "•••" + acc.account[-4:]} if acc else None,
            "dependentes": [{"nome": d.dependent.name, "tipo": d.get_kind_display(), "nascimento": d.dependent.birth_date}
                            for d in deps],
            # Aviso de prova de vida pendente (campanha aberta com aviso no portal)
            "prova_de_vida": [{"campanha": pv.campaign.name, "ato": pv.campaign.legal_act, "prazo": pv.due_date,
                               "suspenso": pv.status == "BLOQUEADO", "orientacoes": pv.campaign.instructions}
                              for pv in _life_proofs(p)],
        })


class BenefitsView(PortalView):
    def get(self, request):
        from apps.concessao.models import Benefit

        rows = Benefit.objects.filter(beneficiary=self.person, institution=self.institution) \
            .select_related("instituidor", "payroll_group").order_by("-start_date")
        return Response([{"id": str(b.pk), "tipo": b.get_kind_display(), "modalidade": b.get_modality_display() or "",
                          "inicio": b.start_date, "fim": b.end_date, "valor": str(b.amount),
                          "situacao": b.get_status_display(), "instituidor": b.instituidor.name if b.instituidor else "",
                          "paridade": b.paridade, "fundamentacao": b.legal_basis} for b in rows])


def _visible_entries(portal):
    """Só contracheques de folhas FECHADAS ou PAGAS (nunca folha em cálculo)."""
    from apps.folha.models import PayrollEntry, RunStatus

    return PayrollEntry.objects.filter(beneficiary=portal.person, institution=portal.institution,
                                       run__status__in=[RunStatus.FECHADA, RunStatus.PAGA])


class PayslipsView(PortalView):
    def get(self, request):
        rows = _visible_entries(request.portal).select_related("run__competence", "run__payroll_group", "benefit") \
            .order_by("-run__competence__year", "-run__competence__month", "run__kind")
        return Response([{"id": str(e.pk), "competencia": str(e.run.competence), "tipo": e.run.get_kind_display(),
                          "beneficio": e.benefit.get_kind_display(), "bruto": str(e.gross), "descontos": str(e.discounts),
                          "liquido": str(e.net), "pago_em": e.run.payment_date} for e in rows[:60]])


class PayslipDetailView(PortalView):
    def get(self, request, pk):
        from apps.folha.serializers import PayrollEntrySerializer

        e = _visible_entries(request.portal).filter(pk=pk).select_related(
            "beneficiary", "benefit__instituidor", "run__competence", "run__payroll_group").prefetch_related("items").first()
        if e is None:
            raise NotFound("Contracheque não encontrado.")
        data = PayrollEntrySerializer(e).data
        data.pop("memory", None)  # memória de cálculo é interna
        data.pop("warnings", None)
        acc = data.get("bank") or {}
        if acc.get("conta"):
            acc["conta"] = "•••" + acc["conta"][-4:]
        return Response(data)


class IncomeReportView(PortalView):
    def get(self, request):
        from apps.folha.services import income_report

        years = sorted({e.run.competence.year for e in _visible_entries(request.portal).select_related("run__competence")},
                       reverse=True)
        year = request.query_params.get("year")
        if not year:
            return Response({"anos": years})
        try:
            year = int(year)
        except ValueError:
            raise serializers.ValidationError({"year": "Ano inválido."})
        if year not in years:
            raise NotFound("Não há folha fechada neste ano.")
        return Response(income_report(self.institution, self.person, year))


class ProcessesView(PortalView):
    """Processos do Protocolo em que o segurado é interessado: situação e andamentos (sem o texto interno dos despachos)."""

    def get(self, request):
        from apps.protocolo.models import Process

        rows = Process.objects.filter(institution=self.institution, interested=self.person) \
            .select_related("process_type", "current_sector").prefetch_related("movements__to_sector").order_by("-opened_at")
        return Response([{
            "id": str(p.pk), "numero": f"{p.number:06d}/{p.year}", "tipo": p.process_type.name, "assunto": p.subject,
            "aberto_em": p.opened_date, "situacao": p.get_status_display(), "setor_atual": p.current_sector.name,
            "andamentos": [{"data": m.occurred_at, "tipo": m.get_kind_display(),
                            "setor": m.to_sector.name if m.to_sector else ""} for m in p.movements.all().order_by("occurred_at")],
        } for p in rows])


class RequestSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    process_code = serializers.SerializerMethodField()

    class Meta:
        model = PortalRequest
        fields = ["id", "kind", "kind_display", "subject", "message", "status", "status_display", "answer",
                  "answered_at", "process_code", "created_at"]
        read_only_fields = ["status", "answer", "answered_at"]

    def get_process_code(self, obj):
        return f"{obj.process.number:06d}/{obj.process.year}" if obj.process_id else ""


class RequestsView(PortalView):
    def get(self, request):
        qs = PortalRequest.objects.filter(person=self.person, institution=self.institution).select_related("process")
        return Response(RequestSerializer(qs, many=True).data)

    def post(self, request):
        ser = RequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if ser.validated_data["kind"] not in RequestKind.values:
            raise serializers.ValidationError({"kind": "Tipo inválido."})
        open_count = PortalRequest.objects.filter(person=self.person, status__in=["ABERTA", "EM_ANALISE"]).count()
        if open_count >= 10:
            raise serializers.ValidationError("Você já tem 10 solicitações em andamento. Aguarde a resposta.")
        req = ser.save(person=self.person, institution=self.institution)
        return Response(RequestSerializer(req).data, status=201)


# ------------------------------------------------------------------ gestão pela equipe do RPPS
class AccessSerializer(serializers.ModelSerializer):
    person_name = serializers.CharField(source="person.name", read_only=True)
    person_cpf = serializers.SerializerMethodField()
    must_change_password = serializers.BooleanField(source="user.must_change_password", read_only=True)
    locked = serializers.BooleanField(source="user.is_locked", read_only=True)

    class Meta:
        model = PortalAccess
        fields = ["id", "person", "person_name", "person_cpf", "active", "last_access", "must_change_password", "locked",
                  "created_at"]

    def get_person_cpf(self, obj):
        return format_cpf(obj.person.cpf)


class AccessAdminViewSet(InstitutionScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Acessos ao portal. POST {person} cria/reemite senha provisória; {id}/deactivate {justification}."""

    module_code = "portal"
    serializer_class = AccessSerializer
    queryset = PortalAccess.objects.select_related("person", "user").all()
    filterset_fields = ["active"]
    action_permissions = {"create": "editar", "deactivate": "editar"}

    def get_queryset(self):
        qs = super().get_queryset()
        term = (self.request.query_params.get("search") or "").strip()
        if term:
            d = only_digits(term)
            qs = qs.filter(Q(person__name__icontains=term) | (Q(person__cpf__startswith=d) if len(d) >= 3 else Q(pk=None)))
        return qs

    def create(self, request, *args, **kwargs):
        from apps.people.models import Person

        person = Person.objects.filter(institution=self.get_institution(), pk=request.data.get("person")).first()
        if person is None:
            raise serializers.ValidationError({"person": "Escolha a pessoa."})
        access, password = services.create_access(self.get_institution(), person)
        return Response({**AccessSerializer(access).data, "senha_provisoria": password,
                         "login": format_cpf(person.cpf)}, status=201)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return Response(AccessSerializer(services.deactivate(self.get_object(), get_justification(request))).data)


class RequestAdminSerializer(RequestSerializer):
    person_name = serializers.CharField(source="person.name", read_only=True)
    person_cpf = serializers.SerializerMethodField()
    answered_by_name = serializers.CharField(source="answered_by.full_name", read_only=True, default="")

    class Meta(RequestSerializer.Meta):
        fields = RequestSerializer.Meta.fields + ["person", "person_name", "person_cpf", "answered_by_name"]

    def get_person_cpf(self, obj):
        return format_cpf(obj.person.cpf)


class RequestAdminViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """Solicitações recebidas pelo portal. {id}/answer {answer, status, process?}."""

    module_code = "portal"
    serializer_class = RequestAdminSerializer
    queryset = PortalRequest.objects.select_related("person", "answered_by", "process").all()
    filterset_fields = ["status", "kind"]
    action_permissions = {"answer": "editar"}

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        from apps.protocolo.models import Process

        req = self.get_object()
        proc = None
        if request.data.get("process"):
            proc = Process.objects.filter(institution=self.get_institution(), pk=request.data["process"]).first()
            if proc is None:
                raise serializers.ValidationError({"process": "Processo não encontrado."})
        if req.person_id is None:
            raise PermissionDenied()
        return Response(RequestAdminSerializer(services.answer_request(
            req, request.user, request.data.get("answer", ""), request.data.get("status", "RESPONDIDA"), proc)).data)


# ------------------------------------------------------------------ prova de vida pelo Portal
class LifeProofView(PortalView):
    """GET: provas de vida do segurado (pendentes e recentes)."""

    def get(self, request):
        from apps.provadevida.models import LifeProof

        rows = (LifeProof.objects.filter(person=self.person, institution=self.institution)
                .exclude(campaign__status="RASCUNHO").select_related("campaign").order_by("-campaign__start_date")[:10])
        return Response([{
            "id": str(p.pk), "campanha": p.campaign.name, "ato": p.campaign.legal_act, "prazo": p.due_date,
            "situacao": p.status, "situacao_texto": p.get_status_display(), "realizada_em": p.done_date,
            "forma": p.get_channel_display() if p.channel else "", "orientacoes": p.campaign.instructions,
            "aceita_portal": p.campaign.allow_portal and p.campaign.status == "ABERTA",
            "campanha_aberta": p.campaign.status == "ABERTA", "motivo_recusa": p.review_note,
            "enviada_em": p.portal_submitted_at,
        } for p in rows])


class LifeProofSubmitView(PortalView):
    """POST multipart: selfie (foto do segurado segurando o documento), documento (foto do documento), declaracao."""

    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request, pk):
        from apps.provadevida import services as pv
        from apps.provadevida.models import LifeProof

        proof = LifeProof.objects.filter(pk=pk, person=self.person, institution=self.institution).first()
        if proof is None:
            raise NotFound("Prova de vida não encontrada.")
        import json

        try:
            liveness = json.loads(request.data.get("vivacidade") or "{}")
        except ValueError:
            liveness = {}
        pv.portal_submit(proof, request.FILES.get("selfie"), request.FILES.get("documento"),
                         str(request.data.get("declaracao")).lower() in ("true", "1", "sim"),
                         frames=request.FILES.getlist("gestos"), liveness=liveness if isinstance(liveness, dict) else {})
        return Response({"ok": True, "situacao": proof.status})


# ------------------------------------------------------------------ avisos (sininho)
class NotificationsView(PortalView):
    def get(self, request):
        from .models import PortalNotification

        qs = PortalNotification.objects.filter(person=self.person, institution=self.institution)[:50]
        return Response({
            "nao_lidos": PortalNotification.objects.filter(person=self.person, read_at__isnull=True).count(),
            "avisos": [{"id": str(n.pk), "nivel": n.level, "titulo": n.title, "mensagem": n.message, "tela": n.tab,
                        "lido": bool(n.read_at), "data": n.created_at} for n in qs],
        })

    def post(self, request):
        """Marca como lido: {id} ou {todos: true}."""
        from .models import PortalNotification

        qs = PortalNotification.objects.filter(person=self.person, read_at__isnull=True)
        if not request.data.get("todos"):
            qs = qs.filter(pk=request.data.get("id"))
        qs.update(read_at=timezone.now())
        return Response({"ok": True})

# ------------------------------------------------------------------ mensagens ao celular (equipe)
class OutboundMessageSerializer(serializers.ModelSerializer):
    person_name = serializers.CharField(source="person.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    whatsapp = serializers.SerializerMethodField()
    sent_by_name = serializers.CharField(source="sent_by.full_name", read_only=True, default="")

    class Meta:
        from .models import OutboundMessage

        model = OutboundMessage
        fields = ["id", "person", "person_name", "channel", "channel_display", "phone", "text", "status",
                  "status_display", "sent_at", "sent_by_name", "provider_response", "created_at", "whatsapp"]

    def get_whatsapp(self, obj):
        from .notifications import whatsapp_link

        return whatsapp_link(obj.phone, obj.text)


class OutboundMessageViewSet(InstitutionScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Mensagens ao celular. ?situacao=PENDENTE. mark-sent / cancel exigem portal:editar."""

    module_code = "portal"
    serializer_class = OutboundMessageSerializer
    action_permissions = {"mark_sent": "editar", "cancel": "editar"}

    def get_queryset(self):
        from .models import OutboundMessage

        qs = OutboundMessage.objects.filter(institution=self.get_institution()).select_related("person", "sent_by")
        if self.request.query_params.get("situacao"):
            qs = qs.filter(status=self.request.query_params["situacao"])
        return qs

    @action(detail=True, methods=["post"], url_path="mark-sent")
    def mark_sent(self, request, pk=None):
        from apps.audit.services import log_event

        m = self.get_object()
        if m.status != "PENDENTE":
            raise serializers.ValidationError("A mensagem não está aguardando envio.")
        m.status, m.sent_at, m.sent_by = "ENVIADA", timezone.now(), request.user
        m.provider_response = (request.data.get("note") or "Enviada manualmente pelo WhatsApp").strip()[:500]
        m.save()
        log_event("UPDATE", module="portal", obj=m, object_repr=f"Mensagem ao celular enviada — {m.person.name}")
        return Response(self.get_serializer(m).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        m = self.get_object()
        if m.status != "PENDENTE":
            raise serializers.ValidationError("A mensagem não está aguardando envio.")
        m.status, m.provider_response = "CANCELADA", (request.data.get("note") or "").strip()[:500]
        m.save()
        return Response(self.get_serializer(m).data)

# ------------------------------------------------------------------ recadastramento pelo Portal
class ReregistrationView(PortalView):
    """GET: recadastramentos do segurado + dados atuais do cadastro (para o formulário já vir preenchido)."""

    def get(self, request):
        from apps.recadastramento import services as rc

        rows = rc.portal_items(self.person)
        return Response({
            "cadastro": rc.snapshot(self.person),
            "itens": [{"id": str(i.pk), "campanha": i.campaign.name, "ato": i.campaign.legal_act, "prazo": i.due_date,
                       "situacao": i.status, "situacao_texto": i.get_status_display(), "motivo_devolucao": i.review_note
                       if i.status == "DEVOLVIDO" else "", "aceita_portal": i.campaign.portal_enabled and i.campaign.status == "ABERTA",
                       "campanha_aberta": i.campaign.status == "ABERTA", "exige_comprovante": i.campaign.require_residence_proof,
                       "orientacoes": i.campaign.instructions, "enviado_em": i.submitted_at} for i in rows],
        })


class ReregistrationSubmitView(PortalView):
    """POST multipart: dados (JSON), declaracoes (JSON), comprovante (arquivo), documento (arquivo, opcional)."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        import json

        from apps.recadastramento import services as rc
        from apps.recadastramento.models import Reregistration

        item = Reregistration.objects.filter(pk=pk, person=self.person, institution=self.institution).first()
        if item is None:
            raise NotFound("Recadastramento não encontrado.")
        try:
            data, decl = json.loads(request.data.get("dados") or "{}"), json.loads(request.data.get("declaracoes") or "{}")
        except ValueError:
            raise serializers.ValidationError("Dados inválidos.")
        rc.submit(item, data, decl, residence=request.FILES.get("comprovante"), id_doc=request.FILES.get("documento"))
        return Response({"ok": True, "situacao": item.status})