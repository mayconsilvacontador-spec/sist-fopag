"""
Origens da base atuarial (leiaute SPREV) a partir do Cadastro Único e dos vínculos:
servidores ativos, dependentes e baixas de servidores.

Campos que dependem de módulos futuros ficam em branco e geram pendência:
remuneração/contribuição (Folha — Fase 5) e tempos averbados (Fase 3).
"""
from django.db.models import Count, Q

from apps.actuarial.sources import source
from apps.core.validators import format_cnpj, format_cpf, only_digits

from .models import EmploymentLink, LinkStatus, Regime


def _pis(value):
    d = only_digits(value)
    return f"{d[:3]}.{d[3:8]}.{d[8:10]}-{d[10:]}" if len(d) == 11 else ""


def _yes_no(flag):
    return 1 if flag else 2


def _organ_fields(organ):
    return {
        "NO_ORGAO": organ.name, "CO_PODER": organ.poder, "CO_TIPO_PODER": organ.tipo_poder,
    }


def _server_row(link, ctx, deps_count):
    p, organ, pos = link.person, link.organ, link.position
    row = {
        "_massa": link.segment, "_lote": link.life_purchase,
        **_organ_fields(organ), "NU_CNPJ_ORGAO": format_cnpj(organ.cnpj) if organ.cnpj else "",
        "CO_TIPO_POPULACAO": 1, "CO_TIPO_CARGO": pos.cargo_type, "CO_CRITERIO_ELEGIBILIDADE": link.eligibility,
        "ID_SERVIDOR_MATRICULA": link.registration, "ID_SERVIDOR_CPF": format_cpf(p.cpf),
        "ID_SERVIDOR_PIS_PASEP": _pis(p.pis_pasep), "CO_SEXO_SERVIDOR": p.sex,
        "CO_EST_CIVIL_SERVIDOR": p.marital_status or "", "DT_NASC_SERVIDOR": p.birth_date,
        "CO_SITUACAO_FUNCIONAL": link.situation, "CO_TIPO_VINCULO": link.link_type,
        "DT_ING_SERV_PUB": link.public_service_start, "DT_ING_ENTE": link.ente_start,
        "DT_ING_CARREIRA": link.career_start, "NO_CARREIRA": pos.career, "DT_ING_CARGO": link.position_start,
        "NO_CARGO": pos.name, "NU_DEPENDENTES": deps_count,
        "IN_ABONO_PERMANENCIA": _yes_no(link.permanence_bonus_since and link.permanence_bonus_since <= ctx.reference_date),
        "DT_INICIO_ABONO": link.permanence_bonus_since, "IN_PREV_COMP": _yes_no(link.complementary_pension),
    }
    if not p.pis_pasep:
        ctx.pendencias.append(f"Matrícula {link.registration}: PIS/PASEP não informado.")
    if not p.marital_status:
        ctx.pendencias.append(f"Matrícula {link.registration}: estado civil não informado.")
    return row


def _links(ctx):
    return (EmploymentLink.objects.filter(institution=ctx.institution, regime=Regime.ESTATUTARIO)
            .select_related("person", "organ", "position", "life_purchase"))


def _deps_counts(ctx, person_ids):
    from apps.people.models import Dependency

    active = Q(start_date__lte=ctx.reference_date) & (Q(end_date__isnull=True) | Q(end_date__gt=ctx.reference_date))
    rows = Dependency.objects.filter(active, holder_id__in=person_ids).values("holder_id").annotate(n=Count("id"))
    return {r["holder_id"]: r["n"] for r in rows}


@source("servidores")
def servidores(ctx):
    links = list(_links(ctx).filter(position_start__lte=ctx.reference_date).filter(
        Q(status=LinkStatus.ATIVO) | Q(end_date__gt=ctx.reference_date)))
    if links:
        ctx.pendencias.append("Servidores: VL_BASE_CALCULO, VL_REMUNERACAO e VL_CONTRIBUICAO virão da Folha (Fase 5).")
        ctx.pendencias.append("Servidores: tempos anteriores (NU_TEMPO_RGPS / RPPS) virão das averbações (Fase 3).")
    counts = _deps_counts(ctx, [lk.person_id for lk in links])
    return [_server_row(lk, ctx, counts.get(lk.person_id, 0)) for lk in links]


@source("servidores_baixas")
def servidores_baixas(ctx):
    rows = []
    links = _links(ctx).filter(status__in=[LinkStatus.EXONERADO, LinkStatus.FALECIDO],
                               end_date__gte=ctx.period_start, end_date__lte=ctx.period_end)
    counts = _deps_counts(ctx, [lk.person_id for lk in links])
    for lk in links:
        row = _server_row(lk, ctx, counts.get(lk.person_id, 0))
        row["CO_SITUACAO"] = 13 if lk.status == LinkStatus.FALECIDO else 12
        row["DT_SITUACAO"] = lk.end_date
        rows.append(row)
    return rows


@source("dependentes")
def dependentes(ctx):
    from apps.people.models import Dependency

    links = {lk.person_id: lk for lk in _links(ctx).filter(position_start__lte=ctx.reference_date).filter(
        Q(status=LinkStatus.ATIVO) | Q(end_date__gt=ctx.reference_date))}
    deps = Dependency.objects.filter(
        holder_id__in=links.keys(), start_date__lte=ctx.reference_date,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=ctx.reference_date)).select_related("holder", "dependent")
    rows = []
    for dep in deps:
        lk, h, d = links[dep.holder_id], dep.holder, dep.dependent
        rows.append({
            "_massa": lk.segment, "_lote": lk.life_purchase,
            **_organ_fields(lk.organ), "CNPJ_ORGAO": format_cnpj(lk.organ.cnpj) if lk.organ.cnpj else "",
            "ID_SEGURADO_MATRICULA": lk.registration, "ID_SEGURADO_CPF": h.cpf,
            "ID_SEGURADO_PIS_PASEP": only_digits(h.pis_pasep), "CO_SEXO_SEGURADO": h.sex,
            "ID_DEPENDENTE": d.cpf, "ID_DEPENDENTE_CPF": d.cpf, "DT_NASC_DEPENDENTE": d.birth_date,
            "CO_SEXO_DEPENDENTE": d.sex, "CO_CONDICAO_DEPENDENTE": 2 if d.is_invalid else 1,
            "CO_TIPO_DEPENDECIA": dep.kind,
        })
    return rows
