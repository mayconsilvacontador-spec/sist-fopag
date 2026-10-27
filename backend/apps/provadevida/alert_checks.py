"""Alertas da Prova de Vida: prazo da campanha chegando e beneficiários que já passaram da tolerância."""
from datetime import timedelta

from django.utils import timezone

from apps.alerts.checks import AlertSpec, check
from apps.alerts.models import Severity

from .models import CampaignStatus, LifeProofCampaign, ProofStatus


@check("PROVA_DE_VIDA")
def prova_de_vida(institution):
    from . import services

    today = timezone.localdate()
    # Efeito colateral intencional: a rotina diária de alertas também gera os lembretes de prazo no Portal
    services.portal_reminders(institution, today)
    specs = []
    for c in LifeProofCampaign.objects.filter(institution=institution, status=CampaignStatus.ABERTA):
        base = dict(module="provadevida.campanhas", link=f"/prova-de-vida/campanhas?c={c.pk}",
                    object_type="provadevida.campaign", object_id=str(c.pk))
        late = services.overdue(c, today).count()
        pending = c.proofs.filter(status=ProofStatus.PENDENTE).count()
        review = c.proofs.filter(status=ProofStatus.EM_ANALISE).count()
        if review:
            specs.append(AlertSpec(Severity.ATENCAO, f"Prova de vida: {review} envio(s) pelo Portal aguardando conferência — {c.name}",
                                   "Confira as fotos em Prova de Vida › Pendentes (situação: em análise).",
                                   **{**base, "link": "/prova-de-vida/pendentes"}, key=f"{c.pk}:review"))
        if late:
            specs.append(AlertSpec(Severity.ATENCAO, f"Prova de vida: {late} beneficiário(s) além do prazo e da tolerância — {c.name}",
                                   "Registre as provas recebidas ou aplique a suspensão prevista no ato "
                                   f"({c.legal_act}) em Prova de Vida › Campanhas.", key=f"{c.pk}:late", **base))
        elif pending and c.end_date <= today + timedelta(days=15):
            specs.append(AlertSpec(Severity.INFORMATIVO, f"Prova de vida: {pending} pendente(s) — campanha termina em "
                                   f"{c.end_date:%d/%m/%Y}", c.name, key=f"{c.pk}:soon", **base))
    return specs
