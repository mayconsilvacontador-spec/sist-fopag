from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.models import Alert, AlertStatus, Severity
from apps.alerts.views import AlertSerializer
from apps.institutions.models import Competence, FiscalYear, PayrollGroup
from apps.institutions.services import get_reference_competence, segments_for_filter

from .providers import SEGMENT_LABELS, get_payroll_provider


class DashboardView(APIView):
    """
    GET /api/v1/dashboard/?plano=<filtro>&exercicio=2026

    plano: TODOS | FINANCEIRO | PREVIDENCIARIO (massa própria + compra de vidas)
           | PREVIDENCIARIO_PROPRIO | COMPRA_VIDAS
    """

    module_code = "painel"

    def get(self, request):
        institution = request.institution
        plano = (request.query_params.get("plano") or "TODOS").upper()
        try:
            exercicio = int(request.query_params.get("exercicio") or timezone.localdate().year)
        except ValueError:
            exercicio = timezone.localdate().year

        fiscal_year = FiscalYear.objects.filter(institution=institution, year=exercicio).first()
        ref = get_reference_competence(institution)
        segments = segments_for_filter(institution, plano)
        groups = PayrollGroup.objects.filter(institution=institution, segment__in=segments, active=True).select_related("plan")
        provider = get_payroll_provider(institution, segments, ref)
        summary = provider.summary()
        series = provider.series()

        order = Case(
            When(severity=Severity.CRITICO, then=Value(0)),
            When(severity=Severity.ATENCAO, then=Value(1)),
            default=Value(2), output_field=IntegerField(),
        )
        open_alerts = Alert.objects.filter(institution=institution, status=AlertStatus.ABERTO)
        alerts_list = open_alerts.annotate(o=order).order_by("o", "-detected_at")[:8]
        next_comp = None
        if ref:
            ny, nm = (ref.year + 1, 1) if ref.month == 12 else (ref.year, ref.month + 1)
            next_comp = Competence.objects.filter(institution=institution, year=ny, month=nm).first()

        def card(key, label, value, fmt):
            return {
                "key": key, "label": label, "format": fmt,
                "value": value if summary else None,
                "source": provider.source, "note": provider.note,
            }

        cards = [
            card("total_beneficiarios", "Total de Beneficiários", summary and summary["beneficiarios"], "int"),
            card("aposentados", "Aposentados", summary and summary["aposentados"], "int"),
            card("pensionistas", "Pensionistas", summary and summary["pensionistas"], "int"),
            card("folha_bruta", "Folha Bruta", summary and summary["bruta"], "currency"),
            card("folha_liquida", "Folha Líquida", summary and summary["liquida"], "currency"),
            card("descontos", "Descontos", summary and summary["descontos"], "currency"),
        ]

        plan_split = []
        if summary and summary.get("por_plano"):
            for kind, vals in summary["por_plano"].items():
                plan_split.append({
                    "plano": SEGMENT_LABELS.get(kind, kind),
                    "massa": kind,
                    "beneficiarios": vals["aposentados"] + vals["pensionistas"],
                    "bruta": vals["bruta"],
                })

        return Response({
            "filtro": {"plano": plano, "exercicio": exercicio,
                       "folhas": [{"id": str(g.pk), "code": g.code, "name": g.name, "massa": g.segment,
                                   "plano": g.plan.code} for g in groups]},
            "cabecalho": {
                "exercicio": {"ano": exercicio, "cadastrado": fiscal_year is not None,
                              "situacao": fiscal_year.get_status_display() if fiscal_year else None},
                "competencia_referencia": {"codigo": str(ref), "rotulo": ref.label,
                                           "situacao": ref.get_status_display()} if ref else None,
                "proxima_competencia": {"codigo": str(next_comp), "rotulo": next_comp.label} if next_comp else None,
                "pendencias": {
                    "total": open_alerts.count(),
                    "criticos": open_alerts.filter(severity=Severity.CRITICO).count(),
                    "demo": open_alerts.filter(is_demo=True).count(),
                    "source": "real",
                },
                "folha": {
                    "status": provider.status(),
                    "competencia": f"{provider.month:02d}/{provider.year}",
                    "source": provider.source,
                    "note": f"Folha mensal de {provider.month:02d}/{provider.year}. Última folha calculada: "
                            f"{(summary or {}).get('competencia_folha') or 'nenhuma'}.",
                },
                "beneficiarios": {
                    "value": summary["beneficiarios"] if summary else None,
                    "source": provider.source, "note": provider.note,
                },
            },
            "avisos": AlertSerializer(alerts_list, many=True).data,
            "cards": cards,
            "graficos": {
                "source": provider.source,
                "note": provider.note,
                "evolucao_folha": [
                    {"rotulo": r["rotulo"], "competencia": r["competencia"], "bruta": r["bruta"],
                     "liquida": r["liquida"], "descontos": r["descontos"]} for r in series
                ],
                "beneficiarios": [
                    {"rotulo": r["rotulo"], "competencia": r["competencia"], "aposentados": r["aposentados"],
                     "pensionistas": r["pensionistas"], "total": r["beneficiarios"]} for r in series
                ],
                "aposentados_pensionistas": [
                    {"nome": "Aposentados", "valor": summary["aposentados"]},
                    {"nome": "Pensionistas", "valor": summary["pensionistas"]},
                ] if summary else [],
                "por_plano": plan_split,
            },
            "gerado_em": timezone.now(),
        })
