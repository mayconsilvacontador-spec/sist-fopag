"""
Apuração do tempo de contribuição.

Fontes:
- vínculos ESTATUTÁRIOS do Cadastro -> natureza 05 (RPPS do órgão de origem);
- vínculos CELETISTAS -> natureza 02 (INSS, órgão público) — dependem de CTC do INSS;
- averbações ativas (naturezas 01 a 04, ou 05 de outro vínculo);
- afastamentos do histórico funcional marcados "não conta como tempo" são descontados.

Regras de contagem:
- dias corridos, incluindo o primeiro e o último dia; 365 dias = 1 ano;
- é vedada a contagem concomitante: períodos sobrepostos são cortados (prioridade
  para o RPPS de origem) e a sobreposição é informada;
- para datas futuras (simulação), o vínculo ativo é projetado até a data, sem
  novos afastamentos.
"""
from django.utils import timezone
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import PUBLIC_SERVICE_NATURES, Averbacao, TimeNature

DAYS_YEAR = 365
TEACHER_CARGO_TYPES = {2}  # professor da educação infantil, ensino fundamental e médio (art. 40, § 5º, CF)


@dataclass
class Period:
    start: date
    end: date | None  # None = vínculo ativo (projetável)
    nature: str
    label: str
    public: bool
    magisterio: bool = False
    special: bool = False
    certified_days: int | None = None  # averbação: dias líquidos da certidão
    extra_days: int = 0
    deductions: list = field(default_factory=list)  # [(início, fim, dias)]
    overlaps: list = field(default_factory=list)  # [(início, fim)] trechos concomitantes desconsiderados
    warnings: list = field(default_factory=list)
    source_id: str = ""

    def end_on(self, on: date) -> date | None:
        end = on if self.end is None else min(self.end, on)
        return end if end >= self.start else None

    def gross_days(self, on: date) -> int:
        end = self.end_on(on)
        return (end - self.start).days + 1 if end else 0

    def deducted_days(self, on: date) -> int:
        total = 0
        for start, end, days in self.deductions:
            if start > on:
                continue
            if days is not None:
                total += days
            else:
                total += (min(end or on, on) - start).days + 1
        return total

    def overlap_days(self, on: date) -> int:
        return sum((min(hi, on) - lo).days + 1 for lo, hi in self.overlaps if lo <= on)

    def net_days(self, on: date) -> int:
        if self.end_on(on) is None:
            return 0
        if self.certified_days is not None and (self.end is not None and self.end <= on):
            net = self.certified_days
        else:
            net = self.gross_days(on) - self.deducted_days(on)
        return max(0, net - self.overlap_days(on))


@dataclass
class TimeSummary:
    on: date
    contribuicao: int
    servico_publico: int
    magisterio: int
    especial: int
    carreira: int
    cargo: int
    conversao: int

    def years(self, attr: str) -> float:
        return getattr(self, attr) / DAYS_YEAR


class PersonTime:
    """Carrega uma vez os períodos da pessoa; `summary(data)` é barato (sem consultas)."""

    def __init__(self, person, reference_link=None):
        from apps.employment.models import EmploymentLink, Regime

        self.person = person
        self.periods: list[Period] = []
        self.warnings: list[str] = []
        links = list(EmploymentLink.objects.filter(person=person).select_related("position", "organ")
                     .prefetch_related("events").order_by("public_service_start"))
        statutory = [lk for lk in links if lk.regime == Regime.ESTATUTARIO]
        active = [lk for lk in statutory if lk.status == "ATIVO"]
        self.link = reference_link or (active[0] if active else (statutory[-1] if statutory else None))

        for lk in links:
            start = (lk.statutory_since or lk.position_start) if lk.regime == Regime.ESTATUTARIO else lk.position_start
            nature = TimeNature.RPPS_ORIGEM if lk.regime == Regime.ESTATUTARIO else TimeNature.INSS_PUBLICO
            p = Period(
                start=start, end=lk.end_date if lk.status != "ATIVO" else None, nature=nature,
                label=f"{lk.organ} — matrícula {lk.registration} ({lk.position.name})", public=True,
                magisterio=lk.position.cargo_type in TEACHER_CARGO_TYPES, special=lk.eligibility == 5,
                source_id=str(lk.pk),
            )
            if lk.regime != Regime.ESTATUTARIO:
                p.warnings.append("Período celetista: exige CTC do INSS para ser contado no RPPS.")
            if lk.statutory_since and lk.regime == Regime.ESTATUTARIO and lk.statutory_since > lk.position_start:
                pre = Period(start=lk.position_start, end=lk.statutory_since - timedelta(days=1),
                             nature=TimeNature.INSS_PUBLICO, label=f"{lk.organ} — período celetista",
                             public=True, source_id=str(lk.pk),
                             warnings=["Período anterior à estatutarização: exige CTC do INSS."])
                self.periods.append(pre)
            for ev in lk.events.all():
                if not ev.counts_as_service:
                    p.deductions.append((ev.start_date, ev.end_date, ev.days))
            self.periods.append(p)

        for av in Averbacao.objects.filter(person=person, active=True).order_by("start_date"):
            self.periods.append(Period(
                start=av.start_date, end=av.end_date, nature=av.nature,
                label=f"Averbação — {av.issuer}" + (f" (CTC {av.certificate_number})" if av.certificate_number else ""),
                public=av.nature in PUBLIC_SERVICE_NATURES, magisterio=av.magisterio, special=av.special_activity,
                certified_days=av.certified_days, extra_days=av.conversion_extra_days, source_id=str(av.pk),
            ))
        self._resolve_overlaps()

    def _resolve_overlaps(self):
        """Corta sobreposições: RPPS de origem tem prioridade; depois, o período mais antigo."""
        order = sorted(self.periods, key=lambda p: (p.nature != TimeNature.RPPS_ORIGEM, p.start))
        taken: list[tuple[date, date]] = []
        far = date(2200, 1, 1)
        for p in order:
            end = p.end or far
            for s, e in taken:
                lo, hi = max(s, p.start), min(e, end)
                if lo <= hi:
                    p.overlaps.append((lo, hi))
            if p.overlaps:
                shown = sum((min(hi, timezone.localdate()) - lo).days + 1 for lo, hi in p.overlaps if lo <= timezone.localdate())
                msg = (f"{p.label}: {shown} dia(s) concomitantes com outro período foram desconsiderados "
                       "(vedada a contagem em dobro).")
                p.warnings.append(msg)
                self.warnings.append(msg)
            taken.append((p.start, end))

    # ---------------------------------------------------------------- consultas
    def summary(self, on: date) -> TimeSummary:
        contrib = public = mag = special = conv = 0
        for p in self.periods:
            days = p.net_days(on)
            contrib += days
            if p.public:
                public += days
            if p.magisterio:
                mag += days
            if p.special:
                special += days
            if p.end and p.end <= on:
                conv += p.extra_days
        lk = self.link
        carreira = cargo = 0
        if lk is not None:
            end = on if lk.status == "ATIVO" else min(lk.end_date, on)
            if end >= lk.position_start:
                cargo = (end - lk.position_start).days + 1
            cstart = lk.career_start or lk.position_start
            if end >= cstart:
                carreira = (end - cstart).days + 1
        return TimeSummary(on=on, contribuicao=contrib + conv, servico_publico=public, magisterio=mag,
                           especial=special, carreira=carreira, cargo=cargo, conversao=conv)

    @property
    def public_service_start(self) -> date | None:
        starts = [p.start for p in self.periods if p.public]
        if self.link is not None:
            starts.append(self.link.public_service_start)
        return min(starts) if starts else None

    @property
    def municipal_effective_start(self) -> date | None:
        """Ingresso em cargo efetivo no ente (vínculos estatutários)."""
        starts = [p.start for p in self.periods if p.nature == TimeNature.RPPS_ORIGEM]
        if self.link is not None:
            starts.append(self.link.ente_start)
        return min(starts) if starts else None

    def detail(self, on: date) -> list[dict]:
        out = []
        for p in sorted(self.periods, key=lambda x: x.start):
            end = p.end_on(on)
            out.append({
                "inicio": p.start, "fim": p.end, "fim_apurado": end, "natureza": p.nature,
                "natureza_display": TimeNature(p.nature).label, "descricao": p.label, "servico_publico": p.public,
                "magisterio": p.magisterio, "especial": p.special, "dias_brutos": p.gross_days(on),
                "deducoes": p.deducted_days(on), "concomitancia": p.overlap_days(on), "acrescimo_conversao": p.extra_days,
                "dias_liquidos": p.net_days(on), "ativo": p.end is None, "avisos": p.warnings,
            })
        return out


def ymd(days: int) -> str:
    """Dias em 'X anos, Y meses e Z dias' (ano de 365 e mês de 30 dias, padrão das certidões)."""
    y, rest = divmod(max(days, 0), 365)
    m, d = divmod(rest, 30)
    return f"{y} ano(s), {m} mês(es) e {d} dia(s)"
