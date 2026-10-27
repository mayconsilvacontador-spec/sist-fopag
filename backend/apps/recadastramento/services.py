"""Regras do Recadastramento (campanha por ato do órgão; nada vai ao Cadastro Único sem conferência da equipe)."""
import hashlib
from datetime import date

from django.core.files.base import ContentFile
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import only_digits

from .models import Audience, CampaignStatus, Channel, Group, Reregistration, Status

PERSON_FIELDS = ["social_name", "marital_status", "education", "race", "phone", "mobile", "email"]
ADDRESS_FIELDS = ["cep", "street", "number", "complement", "district", "city", "uf"]
LABELS = {"social_name": "Nome social", "marital_status": "Estado civil", "education": "Escolaridade",
          "race": "Raça/cor", "phone": "Telefone", "mobile": "Celular", "email": "E-mail", "cep": "CEP",
          "street": "Logradouro", "number": "Número", "complement": "Complemento", "district": "Bairro",
          "city": "Cidade", "uf": "UF"}


# ---------------------------------------------------------------- dados do cadastro
def snapshot(person) -> dict:
    from apps.people.models import Address

    a = Address.objects.filter(person=person, valid_to__isnull=True).first()
    return {
        "pessoa": {k: getattr(person, k) if getattr(person, k) is not None else "" for k in PERSON_FIELDS},
        "endereco": {k: (getattr(a, k) or "") for k in ADDRESS_FIELDS} if a else {k: "" for k in ADDRESS_FIELDS},
    }


def _clean(data: dict) -> dict:
    p, e = data.get("pessoa") or {}, data.get("endereco") or {}
    out = {"pessoa": {}, "endereco": {}}
    for k in PERSON_FIELDS:
        v = p.get(k, "")
        if k in ("marital_status", "race"):
            v = int(v) if str(v).strip() not in ("", "None") else ""
            if k == "race" and v and v not in range(1, 7):
                raise BusinessRuleError("Raça/cor inválida.")
            if k == "marital_status" and v and v not in (1, 2, 3, 4, 5, 6, 9):
                raise BusinessRuleError("Estado civil inválido.")
        else:
            v = str(v or "").strip()[:150]
        out["pessoa"][k] = v
    if out["pessoa"]["email"]:
        try:
            validate_email(out["pessoa"]["email"])
        except ValidationError:
            raise BusinessRuleError("E-mail inválido.")
    mob = only_digits(out["pessoa"]["mobile"])
    if mob and len(mob) not in (10, 11):
        raise BusinessRuleError("Celular inválido: informe com DDD (ex.: (24) 99999-9999).")
    if not (out["pessoa"]["mobile"] or out["pessoa"]["phone"]):
        raise BusinessRuleError("Informe pelo menos um telefone para contato.")
    for k in ADDRESS_FIELDS:
        out["endereco"][k] = str(e.get(k, "") or "").strip()[:150]
    out["endereco"]["cep"] = only_digits(out["endereco"]["cep"])[:8]
    out["endereco"]["uf"] = out["endereco"]["uf"].upper()[:2]
    if not out["endereco"]["street"] or not out["endereco"]["city"]:
        raise BusinessRuleError("Informe o endereço (logradouro e cidade).")
    return out


def changes(item) -> list[dict]:
    """Lista "campo: antes → depois" para a conferência."""
    out = []
    for part in ("pessoa", "endereco"):
        before, after = (item.previous or {}).get(part, {}), (item.proposed or {}).get(part, {})
        for k, v in after.items():
            if str(before.get(k, "")) != str(v):
                out.append({"grupo": part, "campo": k, "rotulo": LABELS.get(k, k), "antes": before.get(k, ""), "depois": v})
    return out


# ---------------------------------------------------------------- campanha
def validate(campaign):
    if campaign.end_date < campaign.start_date:
        raise BusinessRuleError("O fim da campanha é anterior ao início.")
    if len((campaign.legal_act or "").strip()) < 5:
        raise BusinessRuleError("Informe o ato que determinou o recadastramento (ex.: Decreto nº 123/2026).")


def _targets(campaign) -> dict:
    """{pessoa_id: (pessoa, grupo)} — quem já é servidor ativo entra como servidor."""
    from apps.concessao.models import Benefit
    from apps.employment.models import EmploymentLink

    out = {}
    if campaign.audience in (Audience.TODOS, Audience.BENEFICIARIOS):
        for b in Benefit.objects.filter(institution=campaign.institution, status="ATIVO",
                                        beneficiary__death_date__isnull=True).select_related("beneficiary"):
            out[b.beneficiary_id] = (b.beneficiary, Group.BENEFICIARIO)
    if campaign.audience in (Audience.TODOS, Audience.SERVIDORES):
        links = EmploymentLink.objects.filter(institution=campaign.institution, regime="ESTATUTARIO", status="ATIVO",
                                              person__death_date__isnull=True).select_related("person")
        if campaign.organ_id:
            links = links.filter(organ_id=campaign.organ_id)
        for lk in links:
            out[lk.person_id] = (lk.person, Group.SERVIDOR)
    return out


@transaction.atomic
def refresh(campaign, initial=False) -> int:
    if not initial and campaign.status != CampaignStatus.ABERTA:
        raise BusinessRuleError("A campanha não está aberta.")
    have = set(campaign.items.values_list("person_id", flat=True))
    new = [Reregistration(institution=campaign.institution, campaign=campaign, person=p, group=g, due_date=campaign.end_date)
           for pid, (p, g) in _targets(campaign).items() if pid not in have]
    Reregistration.objects.bulk_create(new)
    if not initial:
        for item in Reregistration.objects.filter(pk__in=[n.pk for n in new]).select_related("person", "campaign"):
            _notify_open(item)
    return len(new)


@transaction.atomic
def open_campaign(campaign, user) -> int:
    if campaign.status != CampaignStatus.RASCUNHO:
        raise BusinessRuleError("Só é possível abrir uma campanha em preparação.")
    validate(campaign)
    n = refresh(campaign, initial=True)
    campaign.status, campaign.opened_at = CampaignStatus.ABERTA, timezone.now()
    campaign.save()
    for item in campaign.items.select_related("person"):
        _notify_open(item)
    log_event("UPDATE", module="recadastramento.campanhas", obj=campaign, object_repr=f"Campanha aberta: {campaign}",
              extra={"segurados": n})
    return n


@transaction.atomic
def close_campaign(campaign, user):
    if campaign.status != CampaignStatus.ABERTA:
        raise BusinessRuleError("A campanha não está aberta.")
    campaign.status, campaign.closed_at = CampaignStatus.ENCERRADA, timezone.now()
    campaign.save()
    log_event("UPDATE", module="recadastramento.campanhas", obj=campaign, object_repr=f"Campanha encerrada: {campaign}")
    return campaign


def campaign_stats(campaign) -> dict:
    from django.db.models import Count

    c = {r["status"]: r["n"] for r in campaign.items.values("status").annotate(n=Count("id"))}
    total = sum(c.values())
    late = campaign.items.filter(status__in=[Status.PENDENTE, Status.DEVOLVIDO], due_date__lt=timezone.localdate()).count()
    return {"total": total, **{s: c.get(s, 0) for s in Status.values}, "atrasados": late,
            "percentual": round(100 * c.get(Status.APROVADO, 0) / total, 1) if total else 0}


# ---------------------------------------------------------------- envio, conferência
def _file(upload, label):
    from apps.people.services import ALLOWED_CONTENT_TYPES, MAX_DOCUMENT_BYTES

    if upload.size > MAX_DOCUMENT_BYTES or getattr(upload, "content_type", "") not in ALLOWED_CONTENT_TYPES:
        raise BusinessRuleError(f"{label}: envie PDF, JPG ou PNG de até 10 MB.")
    content = upload.read()
    ext = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else "pdf"
    return content, ext


@transaction.atomic
def submit(item, data: dict, declarations: dict, *, residence=None, id_doc=None, channel=Channel.PORTAL, user=None):
    """Recebe os dados (Portal ou presencial). No presencial, quem atende já confere e aprova em seguida."""
    c = item.campaign
    if c.status != CampaignStatus.ABERTA:
        raise BusinessRuleError("A campanha de recadastramento não está aberta.")
    if channel == Channel.PORTAL and not c.portal_enabled:
        raise BusinessRuleError("Esta campanha não aceita recadastramento pelo Portal. Procure o órgão.")
    if item.status not in (Status.PENDENTE, Status.DEVOLVIDO) and not (channel == Channel.PRESENCIAL and item.status == Status.ENVIADO):
        raise BusinessRuleError("Este recadastramento já foi enviado ou aprovado.")
    if not declarations.get("veracidade"):
        raise BusinessRuleError("Confirme a declaração de que as informações são verdadeiras.")
    clean = _clean(data)
    for upload, field, label in ((residence, "residence_proof", "Comprovante de residência"), (id_doc, "id_document", "Documento")):
        if upload is not None:
            content, ext = _file(upload, label)
            h = hashlib.sha256(content).hexdigest()
            getattr(item, field).save(f"{h[:16]}.{ext}", ContentFile(content), save=False)
            item.file_hashes = {**item.file_hashes, field: h}
    if c.require_residence_proof and not item.residence_proof:
        raise BusinessRuleError("Anexe um comprovante de residência recente (conta de luz, água, telefone…).")
    item.previous, item.proposed = snapshot(item.person), clean
    item.declarations = {k: (str(v)[:1000] if not isinstance(v, bool) else v) for k, v in declarations.items()}
    item.status, item.channel, item.submitted_at, item.review_note = Status.ENVIADO, channel, timezone.now(), ""
    item.save()
    log_event("UPDATE", module="recadastramento.segurados" if item.group == Group.SERVIDOR else "recadastramento.beneficiarios",
              obj=item, object_repr=f"Recadastramento enviado ({item.get_channel_display()}) — {item.person.name}")
    if channel == Channel.PORTAL:
        _notify(item, f"enviado:{int(item.submitted_at.timestamp())}", "Recebemos seu recadastramento",
                "Seus dados serão conferidos pela equipe. Você receberá um aviso com o resultado.", level="INFO")
    elif user is not None:
        approve(item, user, note="Conferido no atendimento presencial.")
    return item


def _followups(item) -> str:
    d = item.declarations or {}
    out = []
    if d.get("dependentes_alteracoes"):
        out.append(f"Dependentes: {d['dependentes_alteracoes']}")
    if d.get("conta_alteracao"):
        out.append(f"Conta bancária: {d['conta_alteracao']}")
    if d.get("acumula_cargo"):
        out.append(f"Declara acumulação de cargo/emprego: {d.get('acumula_cargo_descricao') or 'sem detalhes'}")
    if d.get("outro_beneficio"):
        out.append(f"Declara receber outro benefício previdenciário: {d.get('outro_beneficio_descricao') or 'sem detalhes'}")
    return "\n".join(out)


@transaction.atomic
def approve(item, user, note: str = ""):
    """Aplica no Cadastro Único só o que mudou (endereço ganha nova vigência; o resto fica na auditoria)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.people.models import Address, Document
    from apps.people.services import add_address, upload_document

    if item.status != Status.ENVIADO:
        raise BusinessRuleError("Só é possível aprovar um recadastramento enviado.")
    person = item.person
    applied = {"pessoa": {}, "endereco": {}, "documentos": []}
    current = snapshot(person)
    for k, v in item.proposed.get("pessoa", {}).items():
        if str(current["pessoa"].get(k, "")) != str(v):
            setattr(person, k, v if v != "" or k not in ("marital_status", "race") else None)
            applied["pessoa"][k] = {"antes": current["pessoa"].get(k, ""), "depois": v}
    if applied["pessoa"]:
        person.save()
    addr = item.proposed.get("endereco", {})
    if any(str(current["endereco"].get(k, "")) != str(v) for k, v in addr.items()):
        today = timezone.localdate()
        cur = Address.objects.filter(person=person, valid_to__isnull=True).first()
        if cur and cur.valid_from >= today:
            for k, v in addr.items():
                setattr(cur, k, v)
            cur.save()
        else:
            add_address(person, valid_from=today, **addr)
        applied["endereco"] = {"antes": current["endereco"], "depois": addr}
    for field, doc_type in (("residence_proof", "RESIDENCIA"), ("id_document", "IDENTIDADE")):
        f = getattr(item, field)
        if f:
            h = item.file_hashes.get(field)
            if not Document.objects.filter(person=person, doc_type=doc_type, sha256=h).exists():
                f.open("rb")
                content = f.read()
                f.close()
                ctype = "application/pdf" if f.name.endswith(".pdf") else "image/png" if f.name.endswith(".png") else "image/jpeg"
                upload_document(person, doc_type, SimpleUploadedFile(f.name.rsplit("/", 1)[-1], content, content_type=ctype),
                                description=f"Recadastramento — {item.campaign.name}")
                applied["documentos"].append(doc_type)
    item.applied, item.staff_followup = applied, _followups(item)
    item.status, item.reviewed_by, item.reviewed_at, item.review_note = Status.APROVADO, user, timezone.now(), note.strip()
    item.save()
    log_event("UPDATE", module="cadastros.segurados", obj=person,
              object_repr=f"Cadastro atualizado pelo recadastramento ({item.campaign.name})", extra=applied)
    _notify(item, "aprovado", "Recadastramento concluído",
            f"Seu recadastramento ({item.campaign.name}) foi conferido e aprovado. Obrigado!", level="INFO")
    return item


@transaction.atomic
def give_back(item, user, reason: str):
    if item.status != Status.ENVIADO:
        raise BusinessRuleError("Só é possível devolver um recadastramento enviado.")
    if len((reason or "").strip()) < 10:
        raise BusinessRuleError("Explique ao segurado o que precisa ser corrigido (mínimo de 10 caracteres).")
    item.status, item.review_note, item.reviewed_by, item.reviewed_at = Status.DEVOLVIDO, reason.strip(), user, timezone.now()
    item.save()
    _notify(item, f"devolvido:{int(item.reviewed_at.timestamp())}", "Recadastramento devolvido para correção",
            f"{reason.strip()} Corrija pelo Portal até {item.due_date:%d/%m/%Y} ou procure o órgão.", level="URGENTE")
    return item


# ---------------------------------------------------------------- avisos
def _notify(item, suffix, title, message, level="ATENCAO"):
    from apps.portal.notifications import notify

    notify(item.person, f"rc:{item.pk}:{suffix}", title, message, level=level, tab="recadastramento")


def _notify_open(item):
    how = " Você pode fazer pelo Portal do Segurado." if item.campaign.portal_enabled else " Procure o órgão com seus documentos."
    _notify(item, "aberta", f"Recadastramento: faça até {item.due_date:%d/%m/%Y}",
            f"Está aberto o {item.campaign.name} ({item.campaign.legal_act}).{how}")


def reminders(institution, on: date | None = None) -> int:
    on = on or timezone.localdate()
    n = 0
    for item in (Reregistration.objects.filter(institution=institution, status__in=[Status.PENDENTE, Status.DEVOLVIDO],
                                               campaign__status=CampaignStatus.ABERTA).select_related("campaign", "person")):
        days = (item.due_date - on).days
        if days < 0:
            _notify(item, "vencido", "Prazo do recadastramento vencido",
                    f"O prazo era {item.due_date:%d/%m/%Y}. Faça o recadastramento o quanto antes.", level="URGENTE")
            n += 1
        else:
            stage = min((d for d in (15, 7, 1) if days <= d), default=None)
            if stage is not None:
                _notify(item, f"d{stage}", "Recadastramento: o prazo está acabando",
                        f"Faça seu recadastramento até {item.due_date:%d/%m/%Y} ({item.campaign.name}).",
                        level="URGENTE" if stage <= 7 else "ATENCAO")
                n += 1
    return n


def portal_items(person):
    return (Reregistration.objects.filter(person=person).exclude(campaign__status=CampaignStatus.RASCUNHO)
            .select_related("campaign").order_by("-campaign__start_date")[:10])

