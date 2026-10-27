"""Alertas do COMPREV: exigências com prazo, fluxo do mês anterior não registrado e benefícios sem requerimento."""
from datetime import timedelta

from django.utils import timezone

from apps.alerts.checks import AlertSpec, check
from apps.alerts.models import Severity

from .models import ComprevProcess, Direction, Status


@check("COMPREV")
def comprev(institution):
    from apps.financeiro.services import add_months, month_start

    from . import services

    today = timezone.localdate()
    specs = []
    base = dict(module="comprev.processos", object_type="comprev.process")
    for p in (ComprevProcess.objects.filter(institution=institution, status=Status.EXIGENCIA,
                                            requirement_due__lte=today + timedelta(days=15))
              .select_related("person")):
        late = p.requirement_due < today
        specs.append(AlertSpec(Severity.CRITICO if late else Severity.ATENCAO,
                               f"COMPREV: exigência {'vencida' if late else 'vencendo'} em "
                               f"{p.requirement_due:%d/%m/%Y} — {p.person.name}",
                               p.requirement_text[:250], link=f"/comprev/processos?p={p.pk}", key=f"{p.pk}:exig",
                               object_id=str(p.pk), **base))
    if ComprevProcess.objects.filter(institution=institution, status=Status.DEFERIDO).exists():
        last = add_months(month_start(today), -1)
        f = services.flow(institution, last)
        for d, label, link in ((Direction.RECEBER, "recebimento(s)", "/comprev/recebimentos"),
                               (Direction.PAGAR, "pagamento(s)", "/comprev/pagamentos")):
            n = f["totais"][d]["pendentes"]
            if n:
                specs.append(AlertSpec(Severity.INFORMATIVO, f"COMPREV: {n} {label} de {last:%m/%Y} não registrado(s)",
                                       "Confira o que o COMPREV creditou/debitou e registre em Fluxo Mensal.",
                                       link=link, key=f"fluxo:{d}:{last:%Y-%m}", module="comprev.fluxo",
                                       object_type="comprev.flow", object_id=f"{last:%Y-%m}"))
    n = len(services.potential(institution))
    if n:
        specs.append(AlertSpec(Severity.INFORMATIVO, f"COMPREV: {n} benefício(s) com tempo de outro regime sem requerimento",
                               "Veja o relatório 'Benefícios sem requerimento COMPREV'.", link="/comprev/relatorios",
                               key="potencial", object_id="potencial", **base))
    return specs
