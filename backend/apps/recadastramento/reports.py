"""Relatórios do Recadastramento (tela Recadastramento › Pendências)."""
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.validators import format_cpf
from apps.reports.registry import col, report, result

from . import services
from .models import RegistrationCampaign, Status

CAMP = {"key": "campanha", "label": "Campanha (vazio = a mais recente)", "type": "select", "default": "",
        "options_url": "recadastramento/campanhas", "options": [["", "Mais recente"]]}
GROUP = {"key": "grupo", "label": "Grupo", "type": "select", "default": "",
         "options": [["", "Todos"], ["SERVIDOR", "Servidores ativos"], ["BENEFICIARIO", "Aposentados e pensionistas"]]}


def _campaign(inst, p):
    qs = RegistrationCampaign.objects.filter(institution=inst).exclude(status="RASCUNHO")
    c = qs.filter(pk=p["campanha"]).first() if p.get("campanha") else qs.order_by("-start_date").first()
    if c is None:
        raise BusinessRuleError("Nenhuma campanha de recadastramento aberta ou encerrada.")
    return c


@report("recadastramento-pendentes", "recadastramento.pendencias", "Pendentes de recadastramento",
        "Quem ainda não fez (ou teve o envio devolvido), com prazo e telefone para contato.", [CAMP, GROUP], landscape=True)
def pendentes(inst, p):
    c = _campaign(inst, p)
    today = timezone.localdate()
    qs = c.items.filter(status__in=[Status.PENDENTE, Status.DEVOLVIDO]).select_related("person").order_by("person__name")
    if p.get("grupo"):
        qs = qs.filter(group=p["grupo"])
    rows = [{"nome": i.person.name, "cpf": format_cpf(i.person.cpf), "grupo": i.get_group_display(), "prazo": i.due_date,
             "dias": (i.due_date - today).days, "situacao": i.get_status_display(),
             "telefone": i.person.mobile or i.person.phone, "email": i.person.email} for i in qs]
    return result([col("nome", "Nome"), col("cpf", "CPF"), col("grupo", "Grupo"), col("prazo", "Prazo", "date"),
                   col("dias", "Dias restantes", "int"), col("situacao", "Situação"), col("telefone", "Telefone"),
                   col("email", "E-mail")], rows, {"nome": f"{len(rows)} pendente(s) — {c.name}"})


@report("recadastramento-pendencias-equipe", "recadastramento.pendencias", "Pendências para a equipe",
        "Aprovados que declararam mudança de dependentes, conta bancária, acumulação de cargo ou outro benefício "
        "(exigem providência no cadastro).", [CAMP], landscape=True)
def pendencias_equipe(inst, p):
    c = _campaign(inst, p)
    qs = c.items.filter(status=Status.APROVADO).exclude(staff_followup="").select_related("person").order_by("person__name")
    rows = [{"nome": i.person.name, "cpf": format_cpf(i.person.cpf), "pendencia": i.staff_followup,
             "aprovado": i.reviewed_at.date() if i.reviewed_at else None} for i in qs]
    return result([col("nome", "Nome"), col("cpf", "CPF"), col("pendencia", "Providência"), col("aprovado", "Aprovado em", "date")],
                  rows, {"nome": f"{len(rows)} pendência(s)"})


@report("recadastramento-resumo", "recadastramento.pendencias", "Resumo das campanhas",
        "Quantidade de pessoas, enviados, aprovados, devolvidos e pendentes por campanha.", [])
def resumo(inst, p):
    rows = []
    for c in RegistrationCampaign.objects.filter(institution=inst).exclude(status="RASCUNHO").order_by("-start_date"):
        s = services.campaign_stats(c)
        rows.append({"campanha": c.name, "ato": c.legal_act, "periodo": f"{c.start_date:%d/%m/%Y} a {c.end_date:%d/%m/%Y}",
                     "situacao": c.get_status_display(), "total": s["total"], "aprovados": s["APROVADO"],
                     "enviados": s["ENVIADO"], "devolvidos": s["DEVOLVIDO"], "pendentes": s["PENDENTE"],
                     "percentual": s["percentual"]})
    return result([col("campanha", "Campanha"), col("ato", "Ato"), col("periodo", "Período"), col("situacao", "Situação"),
                   col("total", "Pessoas", "int"), col("aprovados", "Aprovados", "int"), col("enviados", "A conferir", "int"),
                   col("devolvidos", "Devolvidos", "int"), col("pendentes", "Pendentes", "int"),
                   col("percentual", "% concluído", "percent")], rows)
