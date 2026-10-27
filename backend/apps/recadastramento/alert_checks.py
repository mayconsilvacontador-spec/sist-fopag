"""Alertas do Recadastramento: envios aguardando conferência e atrasados. Gera também os lembretes no Portal."""
from django.utils import timezone

from apps.alerts.checks import AlertSpec, check
from apps.alerts.models import Severity

from .models import CampaignStatus, RegistrationCampaign, Status


@check("RECADASTRAMENTO")
def recadastramento(institution):
    from . import services

    today = timezone.localdate()
    services.reminders(institution, today)  # efeito colateral intencional: lembretes de prazo no Portal
    specs = []
    for c in RegistrationCampaign.objects.filter(institution=institution, status=CampaignStatus.ABERTA):
        base = dict(module="recadastramento.campanhas", object_type="recadastramento.campaign", object_id=str(c.pk))
        sent = c.items.filter(status=Status.ENVIADO).count()
        late = c.items.filter(status__in=[Status.PENDENTE, Status.DEVOLVIDO], due_date__lt=today).count()
        if sent:
            specs.append(AlertSpec(Severity.ATENCAO, f"Recadastramento: {sent} envio(s) aguardando conferência — {c.name}",
                                   "Confira em Recadastramento › Segurados / Beneficiários.",
                                   link="/recadastramento/segurados", key=f"{c.pk}:sent", **base))
        if late:
            specs.append(AlertSpec(Severity.INFORMATIVO, f"Recadastramento: {late} pessoa(s) com prazo vencido — {c.name}",
                                   "Veja a lista em Recadastramento › Pendências.", link="/recadastramento/pendencias",
                                   key=f"{c.pk}:late", **base))
    return specs
