"""Regras da Prova de Vida (campanhas por ato do órgão; suspensão e restabelecimento pelo fluxo de benefícios)."""
import calendar
import hashlib
from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from .models import Audience, CampaignStatus, DeadlineRule, LifeProof, ProofStatus


def _benefits(campaign):
    from apps.concessao.models import Benefit

    qs = Benefit.objects.filter(institution=campaign.institution, status="ATIVO", beneficiary__death_date__isnull=True)
    if campaign.audience == Audience.APOSENTADOS:
        qs = qs.filter(kind="APOSENTADORIA")
    elif campaign.audience == Audience.PENSIONISTAS:
        qs = qs.filter(kind="PENSAO")
    if campaign.segment:
        qs = qs.filter(payroll_group__segment=campaign.segment)
    return qs


def due_date_for(campaign, person) -> date:
    """Fim da campanha, ou fim do mês de aniversário que cair dentro do período (se não cair, o fim da campanha)."""
    if campaign.deadline_rule != DeadlineRule.MES_ANIVERSARIO or not person.birth_date:
        return campaign.end_date
    d = date(campaign.start_date.year, campaign.start_date.month, 1)
    while d <= campaign.end_date:
        if d.month == person.birth_date.month:
            last = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
            return min(last, campaign.end_date)
        d = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return campaign.end_date


def validate(campaign):
    if campaign.end_date < campaign.start_date:
        raise BusinessRuleError("O fim da campanha é anterior ao início.")
    if len((campaign.legal_act or "").strip()) < 5:
        raise BusinessRuleError("Informe o ato que determinou a prova de vida (ex.: Decreto nº 123/2026).")


@transaction.atomic
def open_campaign(campaign, user) -> int:
    if campaign.status != CampaignStatus.RASCUNHO:
        raise BusinessRuleError("Só é possível abrir uma campanha em preparação.")
    validate(campaign)
    n = refresh(campaign, initial=True)
    campaign.status, campaign.opened_at = CampaignStatus.ABERTA, timezone.now()
    campaign.save()
    for proof in campaign.proofs.select_related("person"):
        notify_open(proof)
    log_event("UPDATE", module="provadevida.campanhas", obj=campaign, object_repr=f"Campanha aberta: {campaign}",
              extra={"beneficiarios": n})
    return n


@transaction.atomic
def refresh(campaign, initial=False) -> int:
    """Inclui beneficiários que ainda não estão na campanha (ex.: benefício implantado depois da abertura)."""
    if not initial and campaign.status != CampaignStatus.ABERTA:
        raise BusinessRuleError("A campanha não está aberta.")
    have = set(campaign.proofs.values_list("person_id", flat=True))
    people = {b.beneficiary_id: b.beneficiary for b in _benefits(campaign).select_related("beneficiary")}
    new = [LifeProof(institution=campaign.institution, campaign=campaign, person=p, due_date=due_date_for(campaign, p))
           for pid, p in people.items() if pid not in have]
    LifeProof.objects.bulk_create(new)
    return len(new)


@transaction.atomic
def register(proof, user, *, done_date: date, channel: str, notes: str = "", upload=None, password: str = ""):
    """Registra a prova. Se o benefício estava suspenso pela campanha, restabelece (exige senha)."""
    from apps.concessao.models import Benefit
    from apps.concessao.services import event
    from apps.concessao.workflow import confirm_password

    from .models import ProofChannel

    if proof.campaign.status == CampaignStatus.RASCUNHO:
        raise BusinessRuleError("A campanha ainda não foi aberta.")
    if proof.status not in (ProofStatus.PENDENTE, ProofStatus.BLOQUEADO, ProofStatus.EM_ANALISE):
        raise BusinessRuleError("Esta prova de vida já foi registrada ou dispensada.")
    if channel not in ProofChannel.values:
        raise BusinessRuleError("Informe a forma da prova de vida.")
    if done_date > timezone.localdate() or done_date < proof.campaign.start_date - timedelta(days=60):
        raise BusinessRuleError("Data da prova inválida.")
    from_portal = proof.status == ProofStatus.EM_ANALISE
    blocked = proof.status == ProofStatus.BLOQUEADO or (from_portal and proof.status_before_portal == ProofStatus.BLOQUEADO)
    if blocked:
        confirm_password(user, password)
    if upload is not None:
        from apps.people.services import ALLOWED_CONTENT_TYPES, MAX_DOCUMENT_BYTES

        if upload.size > MAX_DOCUMENT_BYTES or getattr(upload, "content_type", "") not in ALLOWED_CONTENT_TYPES:
            raise BusinessRuleError("Comprovante: envie PDF, JPG ou PNG de até 10 MB.")
        content = upload.read()
        proof.attachment_sha256 = hashlib.sha256(content).hexdigest()
        ext = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else "pdf"
        proof.attachment.save(f"{proof.attachment_sha256[:16]}.{ext}", ContentFile(content), save=False)
    restored = []
    if blocked:
        for b in Benefit.objects.filter(pk__in=proof.suspended_benefits, status="SUSPENSO"):
            event(b, "RESTABELECIMENTO", max(done_date, b.start_date),
                  f"Prova de vida realizada em {done_date:%d/%m/%Y} — {proof.campaign.name} ({proof.campaign.legal_act}).",
                  act=proof.campaign.legal_act[:100])
            restored.append(str(b.pk))
    proof.status, proof.done_date, proof.channel = ProofStatus.REALIZADA, done_date, channel
    proof.notes, proof.registered_by = notes.strip(), user
    proof.save()
    _notify(proof, "ok", "Prova de vida confirmada",
            f"Sua prova de vida ({proof.campaign.name}) foi registrada em {done_date:%d/%m/%Y}."
            + (" Seu benefício foi restabelecido." if restored else "") + " Obrigado!", level="INFO")
    log_event("UPDATE", module="provadevida.realizadas", obj=proof,
              object_repr=f"Prova de vida registrada — {proof.person.name}",
              extra={"forma": channel, "restabelecidos": restored})
    return proof, restored


@transaction.atomic
def waive(proof, user, notes: str):
    if proof.status != ProofStatus.PENDENTE:
        raise BusinessRuleError("Só é possível dispensar uma prova pendente.")
    if len((notes or "").strip()) < 15:
        raise BusinessRuleError("Justifique a dispensa (mínimo de 15 caracteres).")
    proof.status, proof.notes, proof.registered_by = ProofStatus.DISPENSADA, notes.strip(), user
    proof.save()
    log_event("UPDATE", module="provadevida.pendentes", obj=proof, object_repr=f"Prova de vida dispensada — {proof.person.name}",
              extra={"justificativa": notes.strip()})
    return proof


def overdue(campaign, on: date | None = None):
    """Pendentes cujo prazo + tolerância já passou."""
    on = on or timezone.localdate()
    return campaign.proofs.filter(status=ProofStatus.PENDENTE, due_date__lt=on - timedelta(days=campaign.grace_days))


@transaction.atomic
def suspend_overdue(campaign, user, password: str) -> dict:
    """Suspende os benefícios de quem não fez a prova no prazo + tolerância (evento SUSPENSAO, auditado)."""
    from apps.concessao.services import event
    from apps.concessao.workflow import confirm_password

    if campaign.status != CampaignStatus.ABERTA:
        raise BusinessRuleError("A campanha não está aberta.")
    confirm_password(user, password)
    today = timezone.localdate()
    people, benefits = 0, 0
    for proof in overdue(campaign, today).select_related("person"):
        ids = []
        for b in _benefits(campaign).filter(beneficiary=proof.person):
            event(b, "SUSPENSAO", max(today, b.start_date),
                  f"Não realização da prova de vida no prazo ({proof.due_date:%d/%m/%Y}) — {campaign.name} "
                  f"({campaign.legal_act}).", act=campaign.legal_act[:100])
            ids.append(str(b.pk))
        proof.status, proof.suspended_at, proof.suspended_benefits = ProofStatus.BLOQUEADO, today, ids
        proof.save()
        _notify(proof, "suspenso", "Benefício suspenso por falta de prova de vida",
                f"Seu benefício foi suspenso porque a prova de vida ({campaign.name}) não foi feita até "
                f"{proof.due_date:%d/%m/%Y}. Faça a prova pelo Portal ou no órgão para restabelecer.", level="URGENTE")
        people += 1
        benefits += len(ids)
    log_event("UPDATE", module="provadevida.bloqueados", obj=campaign,
              object_repr=f"Suspensão por falta de prova de vida — {campaign}", extra={"pessoas": people, "beneficios": benefits})
    return {"pessoas": people, "beneficios": benefits}


@transaction.atomic
def close_campaign(campaign, user):
    if campaign.status != CampaignStatus.ABERTA:
        raise BusinessRuleError("A campanha não está aberta.")
    campaign.status, campaign.closed_at = CampaignStatus.ENCERRADA, timezone.now()
    campaign.save()
    log_event("UPDATE", module="provadevida.campanhas", obj=campaign, object_repr=f"Campanha encerrada: {campaign}")
    return campaign


def portal_pending(person):
    """Prova de vida pendente do segurado (aviso no Portal)."""
    return (LifeProof.objects.filter(person=person, status__in=[ProofStatus.PENDENTE, ProofStatus.BLOQUEADO, ProofStatus.EM_ANALISE],
                                     campaign__status=CampaignStatus.ABERTA, campaign__portal_notice=True)
            .select_related("campaign").order_by("due_date"))


def campaign_stats(campaign) -> dict:
    from django.db.models import Count

    counts = {r["status"]: r["n"] for r in campaign.proofs.values("status").annotate(n=Count("id"))}
    total = sum(counts.values())
    return {"total": total, **{s: counts.get(s, 0) for s in ProofStatus.values},
            "percentual": round(100 * (counts.get("REALIZADA", 0) + counts.get("DISPENSADA", 0)) / total, 1) if total else 0,
            "vencidas": overdue(campaign).count() if campaign.status == CampaignStatus.ABERTA else 0}


# ---------------------------------------------------------------- Portal do Segurado
def _notify(proof, suffix: str, title: str, message: str, level: str = "ATENCAO"):
    if not proof.campaign.portal_notice:
        return
    from apps.portal.notifications import notify

    notify(proof.person, f"pv:{proof.pk}:{suffix}", title, message, level=level, tab="prova-de-vida")


def notify_open(proof):
    how = " Você pode fazer pelo Portal do Segurado, com uma foto sua segurando o documento." if proof.campaign.allow_portal else ""
    _notify(proof, "aberta", "Prova de vida: faça até " + f"{proof.due_date:%d/%m/%Y}",
            f"Está aberta a {proof.campaign.name} ({proof.campaign.legal_act}).{how}", level="ATENCAO")


REMINDER_DAYS = (30, 15, 7, 1)


def portal_reminders(institution, on: date | None = None) -> int:
    """Lembretes de prazo (30, 15, 7 e 1 dia antes) e de prazo vencido. Cada lembrete sai uma vez só."""
    on = on or timezone.localdate()
    n = 0
    proofs = (LifeProof.objects.filter(institution=institution, status=ProofStatus.PENDENTE,
                                       campaign__status=CampaignStatus.ABERTA, campaign__portal_notice=True)
              .select_related("campaign", "person"))
    for p in proofs:
        days = (p.due_date - on).days
        if days < 0:
            _notify(p, "vencido", "Prazo da prova de vida vencido",
                    f"O prazo era {p.due_date:%d/%m/%Y}. Faça a prova de vida o quanto antes para evitar a suspensão do "
                    "benefício.", level="URGENTE")
            n += 1
            continue
        stage = min((d for d in REMINDER_DAYS if days <= d), default=None)
        if stage is not None:
            when = "amanhã" if days <= 1 else f"em {days} dias"
            _notify(p, f"d{stage}", f"Prova de vida: o prazo termina {when}",
                    f"Faça sua prova de vida até {p.due_date:%d/%m/%Y} ({p.campaign.name}).",
                    level="URGENTE" if stage <= 7 else "ATENCAO")
            n += 1
    return n


def _image(upload, label):
    if upload is None:
        raise BusinessRuleError(f"Envie a {label}.")
    if upload.size > 8 * 1024 * 1024:
        raise BusinessRuleError(f"A {label} deve ter até 8 MB.")
    content = upload.read()
    from apps.institutions.branding import sniff

    found = sniff(content)
    if found is None:
        raise BusinessRuleError(f"A {label} deve ser uma foto (JPG, PNG ou WEBP).")
    return content, found[1]


LIVENESS_MIN_FRAMES = 2
LIVENESS_MIN_MOTION = 4.0  # diferença média mínima entre as fotos dos gestos (escala de cinza, 0–255)


def check_liveness(frames: list, liveness: dict) -> dict:
    """
    Verificação de vivacidade feita na câmera ao vivo do Portal: o segurado cumpre gestos sorteados e o navegador
    registra uma foto em cada gesto e mede o movimento entre elas. Aqui o servidor confere que as fotos existem, são
    diferentes entre si e que o movimento medido passou do mínimo. NÃO é biometria facial — a conferência do rosto
    é da equipe (biometria com IA depende de serviço especializado contratado).
    """
    if len(frames) < LIVENESS_MIN_FRAMES:
        raise BusinessRuleError("Faça a selfie pela câmera do Portal, seguindo os gestos pedidos na tela.")
    desafios = [str(d)[:80] for d in (liveness.get("desafios") or [])][:6]
    try:
        movimento = float(liveness.get("movimento") or 0)
    except (TypeError, ValueError):
        movimento = 0.0
    if len(desafios) < LIVENESS_MIN_FRAMES or movimento < LIVENESS_MIN_MOTION:
        raise BusinessRuleError("Não conseguimos confirmar o movimento durante os gestos. Abra a câmera e tente de novo, "
                                "seguindo as instruções da tela.")
    return {"desafios": desafios, "movimento": round(movimento, 1), "camera": str(liveness.get("camera") or "")[:120],
            "navegador": str(liveness.get("navegador") or "")[:200], "metodo": "desafio de gestos + movimento (navegador)"}


@transaction.atomic
def portal_submit(proof, selfie, document, declared: bool, frames=None, liveness: dict | None = None):
    """
    O segurado faz a selfie pela câmera ao vivo (com gestos de vivacidade) e envia a foto do documento; a equipe
    confere e aprova ou recusa. Sem as fotos dos gestos o envio é recusado (não aceita foto da galeria).
    """
    frames = list(frames or [])
    if not declared:
        raise BusinessRuleError("Confirme a declaração de que as fotos são suas e atuais.")
    if proof.campaign.status != CampaignStatus.ABERTA or not proof.campaign.allow_portal:
        raise BusinessRuleError("Esta campanha não aceita prova de vida pelo Portal. Procure o órgão.")
    if proof.status not in (ProofStatus.PENDENTE, ProofStatus.BLOQUEADO):
        raise BusinessRuleError("Sua prova de vida já foi enviada ou registrada.")
    live = check_liveness(frames, liveness or {})
    s, s_ext = _image(selfie, "selfie segurando o documento")
    d, d_ext = _image(document, "foto do documento")
    hs, hd = hashlib.sha256(s).hexdigest(), hashlib.sha256(d).hexdigest()
    if hs == hd:
        raise BusinessRuleError("As duas fotos são iguais. Envie uma selfie e, separadamente, a foto do documento.")
    from django.core.files.storage import default_storage

    paths, hashes = [], set()
    for i, f in enumerate(frames[:6]):
        content, ext = _image(f, f"foto do gesto {i + 1}")
        h = hashlib.sha256(content).hexdigest()
        if h in hashes or h == hs:
            raise BusinessRuleError("As fotos dos gestos estão repetidas. Abra a câmera e tente de novo.")
        hashes.add(h)
        paths.append(default_storage.save(f"provadevida/portal/gestos/{h[:20]}.{ext}", ContentFile(content)))
    live["fotos"] = len(paths)
    proof.portal_selfie.save(f"{hs[:16]}.{s_ext}", ContentFile(s), save=False)
    proof.portal_document.save(f"{hd[:16]}.{d_ext}", ContentFile(d), save=False)
    proof.portal_hashes = {"selfie": hs, "documento": hd, "gestos": sorted(hashes)}
    proof.portal_frames, proof.portal_liveness = paths, live
    proof.status_before_portal, proof.status = proof.status, ProofStatus.EM_ANALISE
    proof.portal_submitted_at, proof.review_note = timezone.now(), ""
    proof.save()
    log_event("UPDATE", module="provadevida.realizadas", obj=proof,
              object_repr=f"Prova de vida enviada pelo Portal — {proof.person.name}", extra=proof.portal_hashes)
    _notify(proof, f"enviada:{hs[:8]}", "Recebemos sua prova de vida",
            "Suas fotos foram enviadas e serão conferidas pela equipe. Você receberá um aviso com o resultado.",
            level="INFO")
    return proof


@transaction.atomic
def portal_reject(proof, user, reason: str):
    if proof.status != ProofStatus.EM_ANALISE:
        raise BusinessRuleError("Esta prova não está em análise.")
    if len((reason or "").strip()) < 10:
        raise BusinessRuleError("Explique ao segurado o motivo da recusa (mínimo de 10 caracteres).")
    proof.status, proof.review_note = proof.status_before_portal or ProofStatus.PENDENTE, reason.strip()
    proof.registered_by = user
    proof.save()
    log_event("UPDATE", module="provadevida.realizadas", obj=proof,
              object_repr=f"Prova de vida do Portal recusada — {proof.person.name}", extra={"motivo": reason.strip()})
    _notify(proof, f"recusada:{proof.portal_hashes.get('selfie', '')[:8]}", "Prova de vida não aceita — envie de novo",
            f"Motivo: {reason.strip()}. Envie novas fotos pelo Portal até {proof.due_date:%d/%m/%Y} ou procure o órgão.",
            level="URGENTE")
    return proof