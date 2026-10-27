"""Integração do Protocolo com a Central de Alertas e a Pesquisa global."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.alerts.checks import AlertSpec, check
from apps.alerts.models import Severity
from apps.core.validators import only_digits
from apps.search.registry import provider

from .models import Process, ProcessStatus


@check("PROTOCOLO_PRAZO_VENCIDO")
def processos_vencidos(institution):
    today = timezone.localdate()
    qs = Process.objects.filter(institution=institution, status=ProcessStatus.EM_TRAMITACAO,
                                due_date__lt=today).select_related("current_sector")
    return [
        AlertSpec(
            Severity.CRITICO, f"Processo {p.code} com prazo vencido",
            f"{p.subject} — venceu em {p.due_date:%d/%m/%Y}. Está no setor {p.current_sector.code}.",
            module="protocolo.processos", link=f"/protocolo/processos/{p.pk}",
            object_type="protocolo.process", object_id=str(p.pk), key=str(p.pk),
        )
        for p in qs
    ]


@check("PROTOCOLO_PRAZO_PROXIMO")
def processos_vencendo(institution):
    today = timezone.localdate()
    qs = Process.objects.filter(institution=institution, status=ProcessStatus.EM_TRAMITACAO,
                                due_date__gte=today, due_date__lte=today + timedelta(days=5))
    return [
        AlertSpec(
            Severity.ATENCAO, f"Processo {p.code} vence em {p.due_date:%d/%m/%Y}",
            p.subject, module="protocolo.processos", link=f"/protocolo/processos/{p.pk}",
            object_type="protocolo.process", object_id=str(p.pk), key=str(p.pk),
        )
        for p in qs
    ]


@provider("processos", "Processos", "protocolo.processos:visualizar")
def search_processes(request, term, limit):
    digits = only_digits(term)
    cond = Q(subject__icontains=term) | Q(interested_name__icontains=term)
    if digits:
        cond |= Q(number=int(digits[:9])) | Q(interested_cpf__startswith=digits)
    qs = Process.objects.filter(cond, institution=request.institution).order_by("-year", "-number")[:limit]
    return [
        {"id": str(p.pk), "title": f"Processo {p.code}", "subtitle": f"{p.subject} · {p.interested_name}",
         "href": f"/protocolo/processos/{p.pk}"}
        for p in qs
    ]


@provider("pessoas", "Cadastro Único", "cadastros.segurados:visualizar")
def search_people(request, term, limit):
    from apps.core.validators import format_cpf
    from apps.people.models import Person

    digits = only_digits(term)
    cond = Q(name__icontains=term) | Q(social_name__icontains=term)
    if len(digits) >= 3:
        cond |= Q(cpf__startswith=digits) | Q(employment_links__registration__icontains=digits)
    qs = Person.objects.filter(cond, institution=request.institution).distinct()[:limit]
    return [
        {"id": str(p.pk), "title": p.name, "subtitle": f"CPF {format_cpf(p.cpf)}", "href": f"/cadastros/pessoas/{p.pk}"}
        for p in qs
    ]
