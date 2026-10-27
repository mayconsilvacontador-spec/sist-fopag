"""Relatórios de Prova de Vida (tela Prova de Vida › Relatórios, mesmo motor dos demais relatórios)."""
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import format_cpf
from apps.reports.registry import col, report, result

from .models import LifeProofCampaign, ProofStatus


def _campaign(inst, p):
    qs = LifeProofCampaign.objects.filter(institution=inst).exclude(status="RASCUNHO")
    c = qs.filter(pk=p["campanha"]).first() if p.get("campanha") else qs.order_by("-start_date").first()
    if c is None:
        raise BusinessRuleError("Nenhuma campanha aberta ou encerrada.")
    return c


CAMP = {"key": "campanha", "label": "Campanha (vazio = a mais recente)", "type": "select", "default": "",
        "options_url": "provadevida/campanhas", "options": [["", "Mais recente"]]}


@report("prova-vida-situacao", "provadevida.relatorios", "Situação da campanha",
        "Todos os beneficiários da campanha com prazo, situação, forma e data da prova.",
        [CAMP, {"key": "situacao", "label": "Situação", "type": "select", "default": "",
                "options": [["", "Todas"]] + [[s.value, s.label] for s in ProofStatus]}], landscape=True)
def situacao(inst, p):
    c = _campaign(inst, p)
    qs = c.proofs.select_related("person").order_by("person__name")
    if p.get("situacao"):
        qs = qs.filter(status=p["situacao"])
    rows = [{"nome": x.person.name, "cpf": format_cpf(x.person.cpf), "nascimento": x.person.birth_date, "prazo": x.due_date,
             "situacao": x.get_status_display(), "forma": x.get_channel_display() if x.channel else "",
             "data": x.done_date, "telefone": x.person.mobile or x.person.phone} for x in qs]
    return result([col("nome", "Beneficiário"), col("cpf", "CPF"), col("nascimento", "Nascimento", "date"),
                   col("prazo", "Prazo", "date"), col("situacao", "Situação"), col("forma", "Forma"),
                   col("data", "Realizada em", "date"), col("telefone", "Telefone")],
                  rows, {"nome": f"{len(rows)} beneficiário(s) — {c.name}"}, [f"Ato: {c.legal_act}"])


@report("prova-vida-resumo", "provadevida.relatorios", "Resumo das campanhas",
        "Quantidade de beneficiários, provas realizadas, dispensadas, pendentes e suspensos por campanha.", [])
def resumo(inst, p):
    from . import services

    rows = []
    for c in LifeProofCampaign.objects.filter(institution=inst).exclude(status="RASCUNHO").order_by("-start_date"):
        s = services.campaign_stats(c)
        rows.append({"campanha": c.name, "ato": c.legal_act, "periodo": f"{c.start_date:%d/%m/%Y} a {c.end_date:%d/%m/%Y}",
                     "situacao": c.get_status_display(), "total": s["total"], "realizadas": s["REALIZADA"],
                     "dispensadas": s["DISPENSADA"], "pendentes": s["PENDENTE"], "suspensos": s["BLOQUEADO"],
                     "percentual": s["percentual"]})
    return result([col("campanha", "Campanha"), col("ato", "Ato"), col("periodo", "Período"), col("situacao", "Situação"),
                   col("total", "Beneficiários", "int"), col("realizadas", "Realizadas", "int"),
                   col("dispensadas", "Dispensadas", "int"), col("pendentes", "Pendentes", "int"),
                   col("suspensos", "Suspensos", "int"), col("percentual", "% concluído", "percent")], rows)
