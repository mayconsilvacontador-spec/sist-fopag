"""Alertas da concessão: cotas temporárias de pensão vencidas ou a vencer."""
from datetime import timedelta

from django.utils import timezone

from apps.alerts.checks import AlertSpec, check
from apps.alerts.models import Severity

from .models import Benefit, BenefitStatus


@check("PENSAO_COTA_VENCIDA")
def cotas_vencidas(institution):
    today = timezone.localdate()
    qs = Benefit.objects.filter(institution=institution, kind="PENSAO", status=BenefitStatus.ATIVO,
                                end_date__isnull=False, end_date__lte=today + timedelta(days=60)).select_related("beneficiary")
    return [
        AlertSpec(
            Severity.CRITICO if b.end_date <= today else Severity.ATENCAO,
            f"Cota de pensão de {b.beneficiary.name or b.beneficiary.cpf} "
            + ("venceu" if b.end_date <= today else "vence") + f" em {b.end_date:%d/%m/%Y}",
            "Cota temporária (cônjuge pela idade ou filho aos 21 anos). Registre a cessação — a cota não é "
            "revertida aos demais dependentes (EC 103, art. 23, § 1º).",
            module="folha.beneficiarios", link=f"/folha/beneficiarios?id={b.pk}",
            object_type="concessao.benefit", object_id=str(b.pk), key=str(b.pk),
        )
        for b in qs
    ]


STAGE_ALERTS = {
    # etapa: (gravidade, setor responsável, o que fazer)
    "ANALISE_JURIDICA": ("ATENCAO", "concessao.juridico", "Aguardando parecer da Procuradoria Jurídica"),
    "CONTROLE_INTERNO": ("ATENCAO", "concessao.controle_interno",
                         "Aguardando análise do Controle Interno — minuta de portaria disponível para Benefícios"),
    "PRESIDENCIA": ("ATENCAO", "concessao.presidencia",
                    "Aguardando assinatura da Presidência — minuta de portaria anexada ao processo"),
    "ATO_EMITIDO": ("ATENCAO", "concessao.implantacao",
                    "Portaria assinada (documento anexado) — providenciar publicação na Notícia Oficial"),
    "PUBLICADO": ("ATENCAO", "concessao.implantacao", "Portaria publicada — implantar na folha"),
}


@check("CONCESSAO_PENDENTE")
def concessoes_pendentes(institution):
    from .models import Concession

    specs = []
    for c in Concession.objects.filter(institution=institution).select_related("person", "process"):
        link = f"/concessao/processo/{c.pk}"
        base = dict(object_type="concessao.concession", object_id=str(c.pk), key=f"{c.pk}:{c.stage}", link=link)
        who = f"{c.get_kind_display()} — {c.person.name} (processo {c.process.code})"
        if c.stage in STAGE_ALERTS:
            sev, module, what = STAGE_ALERTS[c.stage]
            specs.append(AlertSpec(getattr(Severity, sev), f"{what}: {who}", module=module, **base))
        elif c.stage == "CALCULADO" and c.returned_count:
            last = c.steps.filter(action__in=["DEVOLUCAO_JURIDICO", "DEVOLUCAO_CONTROLE"]).order_by("-created_at").first()
            specs.append(AlertSpec(Severity.ATENCAO, f"Processo devolvido para correção: {who}",
                                   last.text if last else "", module="concessao.processos", **base))
        elif c.stage == "SOBRESTADO":
            late = c.suspended_until and c.suspended_until < timezone.localdate()
            specs.append(AlertSpec(
                Severity.ATENCAO if late else Severity.INFORMATIVO,
                (f"Retomada prevista para {c.suspended_until:%d/%m/%Y} vencida — processo sobrestado: {who}" if late
                 else f"Processo sobrestado (pausado){f' até {c.suspended_until:%d/%m/%Y}' if c.suspended_until else ''}: {who}"),
                c.suspension_reason, module="concessao.processos",
                **{**base, "key": f"{c.pk}:SOBRESTADO:{'late' if late else 'ok'}"}))
        elif c.stage == "IMPLANTADO" and not c.tce_sent_date:
            specs.append(AlertSpec(Severity.INFORMATIVO, f"Enviar ao TCE-RJ para registro: {who}",
                                   "Deliberação TCE-RJ 260 — envie os dados (FATIMA / SalContr.txt).",
                                   module="concessao.tce", **base))
        elif c.stage == "IMPLANTADO" and c.tce_result == "ILEGAL":
            specs.append(AlertSpec(Severity.CRITICO, f"TCE-RJ julgou ILEGAL — anular a concessão: {who}",
                                   "Minuta de portaria de anulação disponível no processo.",
                                   module="concessao.presidencia", **base))
    return specs


@check("RGPS_TETO_ANO_AUSENTE")
def teto_rgps_ano(institution):
    """O teto do RGPS muda todo janeiro (Portaria Interministerial MPS/MF) e é usado na folha e nas pensões."""
    from apps.institutions.models import Parameter

    year = timezone.localdate().year
    if Parameter.objects.filter(institution=institution, key="rgps.teto", valid_from__year=year).exists():
        return []
    return [AlertSpec(
        Severity.ATENCAO, f"Teto do RGPS de {year} não cadastrado",
        f"Cadastre o novo teto (parâmetro rgps.teto, vigência 01/01/{year}) conforme a Portaria Interministerial "
        "MPS/MF publicada em janeiro. Até lá, a folha e as pensões usam o teto do ano anterior.",
        module="admin.parametros", link="/administracao/parametros", key=str(year),
    )]
