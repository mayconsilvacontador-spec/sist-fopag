"""
COMPREV (controle).
processos/                 requerimentos (?sentido=RECEBER|PAGAR &situacao= &search=); POST/PATCH dados
processos/<id>/situacao/   muda a situação (enviado, exigência, deferido com valor, indeferido, cessado, cancelado)
processos/<id>/valor/      novo valor mensal com vigência (reajuste/revisão)
processos/<id>/historico/  trilha, valores e lançamentos
processos/potencial/       benefícios com tempo averbado sem requerimento A RECEBER
movimentos/?sentido=…      recebimentos (RECEBER) ou pagamentos (PAGAR); POST lança; lote/; <id>/estornar/; receita/
fluxo/?competencia=AAAA-MM previsto × realizado          indicadores/  painel
"""
from datetime import date

from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import has_perm
from apps.core.validators import format_cpf, only_digits
from apps.core.views import InstitutionScopedMixin

from . import services
from .models import ComprevProcess, Direction, Movement
from .serializers import EventSerializer, MovementSerializer, ProcessSerializer, ValueSerializer


def _date(v, field):
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise serializers.ValidationError({field: "Data inválida."})


def _comp(v):
    try:
        y, m = str(v).split("-")[:2]
        return date(int(y), int(m), 1)
    except (TypeError, ValueError):
        raise serializers.ValidationError({"competence": "Competência inválida (use AAAA-MM)."})


def _money(d):
    return {k: (str(v) if hasattr(v, "quantize") else v) for k, v in d.items()}


class ProcessViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    module_code = "comprev.processos"
    serializer_class = ProcessSerializer
    queryset = ComprevProcess.objects.select_related("person", "plan", "benefit__beneficiary", "averbacao", "ctc")
    action_permissions = {"situacao": "editar", "valor": "editar", "historico": "visualizar",
                          "potencial": "visualizar", "opcoes": "visualizar"}

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("sentido"):
            qs = qs.filter(direction=p["sentido"])
        if p.get("situacao"):
            qs = qs.filter(status__in=p["situacao"].split(","))
        if p.get("pessoa"):
            qs = qs.filter(person=p["pessoa"])
        term = (p.get("search") or "").strip()
        if term:
            digits = only_digits(term)
            from django.db.models import Q

            cond = Q(person__name__icontains=term) | Q(request_number__icontains=term) | \
                Q(counterpart_name__icontains=term)
            if len(digits) >= 3:
                cond |= Q(person__cpf__startswith=digits)
            qs = qs.filter(cond)
        return qs

    def perform_create(self, serializer):
        inst = self.get_institution()
        obj = ComprevProcess(institution=inst, **serializer.validated_data)
        services.validate_process(obj)
        serializer.save(institution=inst, plan=obj.plan, benefit_kind=obj.benefit_kind,
                        counterpart_cnpj=obj.counterpart_cnpj, counterpart_name=obj.counterpart_name,
                        benefit_start=obj.benefit_start)

    def perform_update(self, serializer):
        obj = serializer.save()
        services.validate_process(obj)
        obj.save()

    @action(detail=True, methods=["post"])
    def situacao(self, request, pk=None):
        d = request.data
        p = services.change_status(
            self.get_object(), d.get("status", ""), when=_date(d.get("date"), "date"), note=d.get("note") or "",
            comp_start=_comp(d["comp_start"]) if d.get("comp_start") else None, amount=d.get("amount"),
            backlog=d.get("backlog") or 0,
            requirement_due=_date(d["requirement_due"], "requirement_due") if d.get("requirement_due") else None,
            ended_at=_comp(d["ended_at"]) if d.get("ended_at") else None)
        return Response(ProcessSerializer(p).data)

    @action(detail=True, methods=["post"])
    def valor(self, request, pk=None):
        p = self.get_object()
        services.add_value(p, _comp(request.data.get("valid_from")), request.data.get("amount"),
                           request.data.get("reason") or "")
        return Response(ProcessSerializer(p).data)

    @action(detail=True, methods=["get"])
    def historico(self, request, pk=None):
        p = self.get_object()
        return Response({
            "eventos": EventSerializer(p.events.select_related("created_by"), many=True).data,
            "valores": ValueSerializer(p.values.all(), many=True).data,
            "movimentos": MovementSerializer(p.movements.select_related("process__person", "plan")
                                             .order_by("-competence", "-date"), many=True).data,
        })

    @action(detail=False, methods=["get"])
    def opcoes(self, request):
        """Para o formulário: benefícios, averbações e CTCs da pessoa (sem exigir permissão de outros módulos)."""
        from django.db.models import Q

        from apps.concessao.models import Benefit
        from apps.previdencia.models import Averbacao, Ctc

        inst, pid = self.get_institution(), request.query_params.get("pessoa")
        if not pid:
            raise serializers.ValidationError({"pessoa": "Informe a pessoa."})
        bens = (Benefit.objects.filter(institution=inst).filter(Q(kind="APOSENTADORIA", beneficiary=pid) |
                                                                 Q(kind="PENSAO", instituidor=pid))
                .select_related("beneficiary", "payroll_group__plan").order_by("-start_date"))
        seen, benefits = set(), []
        for b in bens:  # pensão com várias cotas: uma opção por pensão (a primeira cota representa)
            k = (b.kind, b.start_date) if b.kind == "PENSAO" else b.pk
            if k in seen:
                continue
            seen.add(k)
            benefits.append({"id": str(b.pk), "label": f"{b.get_kind_display()} — {b.beneficiary.name} desde "
                             f"{b.start_date:%d/%m/%Y} ({b.get_status_display().lower()})",
                             "kind": "PENSAO" if b.kind == "PENSAO" else "APOSENTADORIA",
                             "start_date": b.start_date, "amount": str(b.amount), "plan": str(b.payroll_group.plan_id),
                             "plan_code": b.payroll_group.plan.code})
        avs = Averbacao.objects.filter(institution=inst, person=pid, active=True).order_by("start_date")
        ctcs = Ctc.objects.filter(institution=inst, person=pid, status="EMITIDA")
        return Response({
            "beneficios": benefits,
            "averbacoes": [{"id": str(a.pk), "label": f"{a.issuer} — {a.start_date:%d/%m/%Y} a {a.end_date:%d/%m/%Y} "
                            f"({a.certified_days} dias){'' if a.comprev else ' · não marcada p/ COMPREV'}",
                            "days": a.certified_days, "nature": a.nature, "issuer": a.issuer,
                            "issuer_cnpj": a.issuer_cnpj} for a in avs],
            "ctcs": [{"id": str(c.pk), "label": f"CTC {c.code} — {c.destination} ({c.period_start:%d/%m/%Y} a "
                      f"{c.period_end:%d/%m/%Y})", "destination": c.destination} for c in ctcs],
        })

    @action(detail=False, methods=["get"])
    def potencial(self, request):
        rows = services.potential(self.get_institution())
        return Response([{"benefit": str(b.pk), "kind": b.get_kind_display(), "beneficiary": b.beneficiary.name,
                          "person": str(owner.pk), "person_name": owner.name, "person_cpf": format_cpf(owner.cpf),
                          "start_date": b.start_date, "amount": str(b.amount), "plan": b.payroll_group.plan.code}
                         for b, owner in rows])


class MovementViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Sempre com ?sentido=RECEBER (Recebimentos) ou PAGAR (Pagamentos): a permissão é a da tela."""

    serializer_class = MovementSerializer
    queryset = Movement.objects.select_related("process__person", "plan")
    action_permissions = {"create": "incluir", "lote": "incluir", "estornar": "editar", "receita": "incluir"}

    @property
    def direction(self):
        d = self.request.query_params.get("sentido") or ""
        if d not in Direction.values:
            raise serializers.ValidationError({"sentido": "Informe o sentido (RECEBER ou PAGAR)."})
        return d

    @property
    def module_code(self):
        return services.MODULE.get(self.request.query_params.get("sentido") or "", "comprev.recebimentos")

    def get_queryset(self):
        qs = super().get_queryset().filter(direction=self.direction)
        p = self.request.query_params
        if p.get("competencia"):
            qs = qs.filter(competence=_comp(p["competencia"]))
        if p.get("processo"):
            qs = qs.filter(process=p["processo"])
        if p.get("ativos") == "1":
            qs = qs.filter(active=True)
        if p.get("sem_receita") == "1":
            qs = qs.filter(revenue__isnull=True)
        return qs

    def _process(self, pk):
        p = ComprevProcess.objects.filter(institution=self.get_institution(), direction=self.direction, pk=pk).first()
        if p is None:
            raise serializers.ValidationError({"process": "Escolha o requerimento."})
        return p

    def create(self, request, *args, **kwargs):
        d = request.data
        m = services.register(self._process(d.get("process")), kind=d.get("kind") or "MENSAL",
                              competence=_comp(d.get("competence")), amount=d.get("amount"),
                              when=_date(d.get("date"), "date"), document=d.get("document") or "")
        return Response(MovementSerializer(m).data, status=201)

    @action(detail=False, methods=["post"])
    def lote(self, request):
        d = request.data
        ms = services.register_batch(self.get_institution(), self.direction, _comp(d.get("competence")),
                                     _date(d.get("date"), "date"), d.get("document") or "", d.get("items") or [])
        return Response({"lancados": len(ms)}, status=201)

    @action(detail=True, methods=["post"])
    def estornar(self, request, pk=None):
        return Response(MovementSerializer(services.reverse(self.get_object(), request.data.get("reason") or "")).data)

    @action(detail=False, methods=["post"])
    def receita(self, request):
        from apps.financeiro.models import TreasuryAccount

        if self.direction != Direction.RECEBER:
            raise serializers.ValidationError("Só recebimentos viram receita.")
        if not has_perm(request, "arrecadacao.receitas:incluir"):
            raise PermissionDenied("Seu perfil não tem permissão para lançar receitas no Financeiro.")
        inst = self.get_institution()
        account = None
        if request.data.get("account"):
            account = TreasuryAccount.objects.filter(institution=inst, pk=request.data["account"]).first()
            if account is None:
                raise serializers.ValidationError({"account": "Conta inválida."})
        rev = services.to_revenue(inst, request.data.get("ids") or [], account)
        return Response({"receita": str(rev.pk), "valor": str(rev.amount)}, status=201)


class FlowView(InstitutionScopedMixin, APIView):
    module_code = "comprev.fluxo"

    def get(self, request):
        comp = _comp(request.query_params.get("competencia")) if request.query_params.get("competencia") else \
            timezone.localdate().replace(day=1)
        f = services.flow(self.get_institution(), comp, request.query_params.get("sentido") or None)
        f["linhas"] = [_money(r) for r in f["linhas"]]
        f["totais"] = {k: _money(v) for k, v in f["totais"].items()}
        f["saldo"] = str(f["saldo"])
        return Response(f)


class IndicatorsView(InstitutionScopedMixin, APIView):
    module_code = "comprev.indicadores"

    def get(self, request):
        i = services.indicators(self.get_institution())
        i["fluxo_mensal_vigente"] = _money(i["fluxo_mensal_vigente"])
        i["ultimos_12_meses"] = [_money(m) for m in i["ultimos_12_meses"]]
        i["atrasados"] = {k: _money(v) for k, v in i["atrasados"].items()}
        return Response(i)
