"""
Indicadores de folha e beneficiários do Painel Geral — sempre dados REAIS do SIST.

- Beneficiários (aposentados/pensionistas): benefícios ATIVOS implantados, por massa — aparecem mesmo antes
  da primeira folha.
- Valores (bruta, descontos, líquida): última competência com folha mensal calculada (inclui folhas ainda não
  fechadas); sem folha calculada, ficam vazios.
- Séries de 12 meses: totais das folhas mensais calculadas de cada competência.
"""
from decimal import Decimal

from django.db.models import Count
from django.utils import timezone

from apps.institutions.models import MONTH_NAMES, Segment

SEGMENT_LABELS = {
    Segment.FINANCEIRO: "Financeiro",
    Segment.PREVIDENCIARIO: "Previdenciário",
    Segment.COMPRA_VIDAS: "Compra de Vidas",
}


def _months_back(year: int, month: int, n: int = 12):
    out = []
    y, m = year, month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(out))


class RealPayrollProvider:
    source = "real"

    def __init__(self, institution, segments, ref):
        self.institution, self.segments = institution, segments
        today = timezone.localdate()
        self.year, self.month = (ref.year, ref.month) if ref else (today.year, today.month)
        self._series = None

    @property
    def note(self) -> str:
        return ("Beneficiários: benefícios ativos implantados. Valores: folha mensal calculada mais recente."
                if self.last_run_month() else
                "Beneficiários: benefícios ativos implantados. Valores aparecem após calcular a primeira folha mensal.")

    def _runs(self):
        from apps.folha.models import PayrollRun, RunKind, RunStatus

        return (PayrollRun.objects.filter(institution=self.institution, kind=RunKind.MENSAL,
                                          payroll_group__segment__in=self.segments)
                .exclude(status=RunStatus.ABERTA).select_related("competence", "payroll_group"))

    def series(self):
        if self._series is not None:
            return self._series
        months = _months_back(self.year, self.month, 12)
        by_month: dict = {}
        for r in self._runs().filter(competence__year__gte=months[0][0]):
            by_month.setdefault((r.competence.year, r.competence.month), []).append(r)
        rows = []
        for y, m in months:
            total = {"aposentados": 0, "pensionistas": 0, "bruta": Decimal(0), "descontos": Decimal(0),
                     "liquida": Decimal(0)}
            for r in by_month.get((y, m), []):
                t = r.totals or {}
                total["aposentados"] += t.get("aposentados", 0)
                total["pensionistas"] += t.get("pensionistas", 0)
                total["bruta"] += Decimal(t.get("proventos", "0"))
                total["descontos"] += Decimal(t.get("descontos", "0"))
                total["liquida"] += Decimal(t.get("liquido", "0"))
            rows.append({"competencia": f"{m:02d}/{y}", "rotulo": f"{MONTH_NAMES[m - 1][:3]}/{str(y)[2:]}",
                         **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in total.items()},
                         "beneficiarios": total["aposentados"] + total["pensionistas"]})
        self._series = rows
        return rows

    def last_run_month(self):
        r = self._runs().order_by("-competence__year", "-competence__month").first()
        return (r.competence.year, r.competence.month) if r else None

    def summary(self):
        from apps.concessao.models import Benefit, BenefitStatus

        counts = {s: {"aposentados": 0, "pensionistas": 0, "bruta": "0"} for s in self.segments}
        rows = (Benefit.objects.filter(institution=self.institution, status=BenefitStatus.ATIVO,
                                       payroll_group__segment__in=self.segments)
                .values("payroll_group__segment", "kind").annotate(n=Count("id")))
        for r in rows:
            key = "aposentados" if r["kind"] == "APOSENTADORIA" else "pensionistas"
            counts[r["payroll_group__segment"]][key] += r["n"]
        out = {"aposentados": sum(c["aposentados"] for c in counts.values()),
               "pensionistas": sum(c["pensionistas"] for c in counts.values()),
               "bruta": None, "descontos": None, "liquida": None, "competencia_folha": None}
        last = self.last_run_month()
        if last:
            totals = {"bruta": Decimal(0), "descontos": Decimal(0), "liquida": Decimal(0)}
            for r in self._runs().filter(competence__year=last[0], competence__month=last[1]):
                t = r.totals or {}
                totals["bruta"] += Decimal(t.get("proventos", "0"))
                totals["descontos"] += Decimal(t.get("descontos", "0"))
                totals["liquida"] += Decimal(t.get("liquido", "0"))
                counts[r.payroll_group.segment]["bruta"] = t.get("proventos", "0")
            out.update({k: str(v) for k, v in totals.items()})
            out["competencia_folha"] = f"{last[1]:02d}/{last[0]}"
        out["beneficiarios"] = out["aposentados"] + out["pensionistas"]
        out["por_plano"] = counts
        return out

    def status(self) -> str:
        """Situação da(s) folha(s) mensal(is) da competência de referência."""
        from apps.folha.models import PayrollRun, RunKind

        runs = list(PayrollRun.objects.filter(institution=self.institution, kind=RunKind.MENSAL,
                                              payroll_group__segment__in=self.segments,
                                              competence__year=self.year, competence__month=self.month))
        if not runs:
            return "Não aberta"
        labels = sorted({r.get_status_display() for r in runs})
        return labels[0] if len(labels) == 1 else " / ".join(labels)


def get_payroll_provider(institution, segments, ref):
    """segments: massas (folhas) incluídas no filtro — ver institutions.services.segments_for_filter."""
    return RealPayrollProvider(institution, segments, ref)
