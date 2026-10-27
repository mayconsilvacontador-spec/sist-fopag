"""Geração, revalidação, exportação e registro de retorno dos eventos do eSocial RPPS."""
import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from . import builders
from .models import EsocialEvent, EsocialLog, EventStatus, EventType
from .validation import validate_xsd

ACTIVE = ~Q(status=EventStatus.SUBSTITUIDO)  # rejeitado continua "ativo" até ser corrigido (substituído)


def _log(ev: EsocialEvent, action: str, detail: str = "", user=None):
    EsocialLog.objects.create(institution=ev.institution, event=ev, action=action, detail=detail[:2000], user=user)


def _new_id(ctx: builders.Ctx) -> str:
    stamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
    prefix = f"ID1{ctx.nr_insc.rjust(14, '0')[:14]}{stamp}"
    seq = EsocialEvent.objects.filter(event_id__startswith=prefix).count() + 1
    return f"{prefix}{seq:05d}"


def _object(ev: EsocialEvent):
    from apps.concessao.models import Benefit
    from apps.folha.models import PayrollRun, Rubric
    from apps.people.models import Person

    if ev.object_type == "people.person":
        return Person.objects.get(pk=ev.object_id)
    if ev.object_type == "concessao.benefit":
        return Benefit.objects.select_related("beneficiary", "instituidor", "payroll_group", "concession").get(pk=ev.object_id)
    if ev.object_type == "folha.rubric":
        return Rubric.objects.get(pk=ev.object_id)
    if ev.object_type == "folha.run_person":
        run_id, person_id = ev.object_id.split(":")
        return PayrollRun.objects.select_related("competence").get(pk=run_id), Person.objects.get(pk=person_id)
    return None


def _build(ctx: builders.Ctx, event_type: str, obj, event_id: str, receipt: str | None, extra: dict) -> str:
    if event_type == "S-2400":
        return builders.s2400(ctx, event_id, obj, receipt)
    if event_type == "S-2410":
        return builders.s2410(ctx, event_id, obj, receipt, cad_ini=extra.get("cad_ini", False))
    if event_type == "S-2420":
        return builders.s2420(ctx, event_id, obj, receipt)
    if event_type == "S-1010":
        return builders.s1010(ctx, event_id, obj)
    if event_type == "S-1207":
        return builders.s1207(ctx, event_id, *obj, receipt)
    if event_type == "S-1210":
        return builders.s1210(ctx, event_id, *obj, receipt)
    if event_type == "S-1299":
        return builders.s1299(ctx, event_id, extra["period"], extra["remun"], extra["pgtos"])
    raise BusinessRuleError("Evento não suportado.")


def _finish(ctx: builders.Ctx, event_type: str, xml: str) -> tuple[list[str], str]:
    pend = list(dict.fromkeys(ctx.pend))
    xsd = validate_xsd(builders.ROOTS[event_type], xml)
    if xsd:
        pend += xsd
    return pend, EventStatus.PENDENTE if pend else EventStatus.VALIDADO


def create_event(institution, event_type: str, *, obj, object_type: str, object_id: str, reference: str,
                 period: str = "", cpf: str = "", replaces: EsocialEvent | None = None, user=None,
                 extra: dict | None = None) -> EsocialEvent:
    base = builders.Ctx.load(institution)
    ctx = base.fresh()
    event_id = _new_id(base)
    receipt = replaces.receipt if replaces is not None and replaces.status == EventStatus.ACEITO else None
    xml = _build(ctx, event_type, obj, event_id, receipt, extra or {})
    pend, status = _finish(ctx, event_type, xml)
    ev = EsocialEvent.objects.create(
        institution=institution, event_type=event_type, event_id=event_id, status=status, retification=bool(receipt),
        replaces=replaces, object_type=object_type, object_id=object_id, reference=reference[:200], period=period,
        cpf=cpf, xml=xml, pendencies=pend, layout_version=base.version, environment=base.environment)
    _log(ev, "GERADO", ("Retificação do recibo " + receipt) if receipt else "", user)
    return ev


# ------------------------------------------------------------------ geração
def _active(institution, event_type, object_type, object_id):
    return EsocialEvent.objects.filter(institution=institution, event_type=event_type, object_type=object_type,
                                       object_id=str(object_id)).filter(ACTIVE)


def _ensure_benefit_number(b):
    if b.esocial_nr:
        return
    from apps.concessao.models import Benefit

    if b.registration and not Benefit.objects.filter(institution=b.institution, esocial_nr=b.registration).exists():
        b.esocial_nr = b.registration[:20]
    else:
        n = Benefit.objects.filter(institution=b.institution).exclude(esocial_nr="").count() + 1
        while Benefit.objects.filter(institution=b.institution, esocial_nr=f"SIST{n:08d}").exists():
            n += 1
        b.esocial_nr = f"SIST{n:08d}"
    Benefit.objects.filter(pk=b.pk).update(esocial_nr=b.esocial_nr)


@transaction.atomic
def generate_registrations(institution, user=None) -> dict:
    """S-2400 (beneficiário), S-2410 (benefício) e S-2420 (término) que ainda não foram gerados."""
    from apps.concessao.models import Benefit
    from apps.institutions.services import get_parameter

    start = get_parameter(institution, "esocial.inicio_rpps")
    start = date.fromisoformat(start) if start else None
    out = {"S-2400": 0, "S-2410": 0, "S-2420": 0}
    benefits = (Benefit.objects.filter(institution=institution)
                .select_related("beneficiary", "instituidor", "payroll_group", "concession").order_by("start_date"))
    for b in benefits:
        p = b.beneficiary
        if not _active(institution, "S-2400", "people.person", p.pk).exists():
            create_event(institution, "S-2400", obj=p, object_type="people.person", object_id=str(p.pk),
                         reference=f"{p.name} — cadastro do beneficiário", cpf=p.cpf, user=user)
            out["S-2400"] += 1
        _ensure_benefit_number(b)
        if not _active(institution, "S-2410", "concessao.benefit", b.pk).exists():
            cad_ini = b.legacy_id is not None or (start is not None and b.start_date < start)
            create_event(institution, "S-2410", obj=b, object_type="concessao.benefit", object_id=str(b.pk),
                         reference=f"{p.name} — {b.get_kind_display()} nº {b.esocial_nr}", cpf=p.cpf, user=user,
                         extra={"cad_ini": cad_ini})
            out["S-2410"] += 1
        if b.status == "CESSADO" and b.end_date and \
                not _active(institution, "S-2420", "concessao.benefit", b.pk).exists():
            create_event(institution, "S-2420", obj=b, object_type="concessao.benefit", object_id=str(b.pk),
                         reference=f"{p.name} — término do benefício nº {b.esocial_nr}", cpf=p.cpf, user=user)
            out["S-2420"] += 1
    log_event("CREATE", module="esocial.eventos", object_repr="Geração de eventos cadastrais", extra=out)
    return out


@transaction.atomic
def generate_rubrics(institution, user=None) -> dict:
    from apps.folha.models import Rubric

    n = 0
    for r in Rubric.objects.filter(institution=institution, active=True).order_by("code", "version"):
        if not _active(institution, "S-1010", "folha.rubric", r.pk).exists():
            create_event(institution, "S-1010", obj=r, object_type="folha.rubric", object_id=str(r.pk),
                         reference=f"Rubrica {r.code} v{r.version} — {r.name}", user=user)
            n += 1
    return {"S-1010": n}


@transaction.atomic
def generate_payroll(run, user=None) -> dict:
    from apps.folha.models import RunStatus

    if run.status not in (RunStatus.FECHADA, RunStatus.PAGA):
        raise BusinessRuleError("O S-1207 é gerado a partir de folha FECHADA (e o S-1210, de folha PAGA).")
    out = {"S-1207": 0, "S-1210": 0}
    per = builders.period_of(run)[1]
    people = {e.beneficiary_id: e.beneficiary for e in run.entries.select_related("beneficiary", "benefit")}
    for e in run.entries.select_related("benefit"):
        _ensure_benefit_number(e.benefit)
    for pid, p in people.items():
        oid = f"{run.pk}:{pid}"
        if not _active(run.institution, "S-1207", "folha.run_person", oid).exists():
            create_event(run.institution, "S-1207", obj=(run, p), object_type="folha.run_person", object_id=oid,
                         reference=f"{p.name} — benefícios {per} ({run.payroll_group.code})", period=per, cpf=p.cpf,
                         user=user)
            out["S-1207"] += 1
        if run.status == RunStatus.PAGA and not _active(run.institution, "S-1210", "folha.run_person", oid).exists():
            create_event(run.institution, "S-1210", obj=(run, p), object_type="folha.run_person", object_id=oid,
                         reference=f"{p.name} — pagamento {per} ({run.payroll_group.code})",
                         period=run.payment_date.strftime("%Y-%m"), cpf=p.cpf, user=user)
            out["S-1210"] += 1
    return out


@transaction.atomic
def close_period(institution, period: str, user=None) -> EsocialEvent:
    """S-1299 do período (AAAA-MM, ou AAAA para o 13º)."""
    if not (len(period) == 4 or (len(period) == 7 and period[4] == "-")):
        raise BusinessRuleError("Período inválido (use AAAA-MM, ou AAAA para o 13º).")
    evs = EsocialEvent.objects.filter(institution=institution, period=period).filter(ACTIVE)
    blocking = evs.filter(event_type__in=["S-1207", "S-1210"]).exclude(status=EventStatus.ACEITO)
    if blocking.exists():
        raise BusinessRuleError(f"Há {blocking.count()} evento(s) S-1207/S-1210 do período ainda não aceitos.")
    if _active(institution, "S-1299", "periodo", period).exclude(status=EventStatus.REJEITADO).exists():
        raise BusinessRuleError("O fechamento (S-1299) deste período já foi gerado.")
    return create_event(institution, "S-1299", obj=None, object_type="periodo", object_id=period,
                        reference=f"Fechamento dos eventos periódicos — {period}", period=period, user=user,
                        extra={"period": period, "remun": evs.filter(event_type="S-1207").exists(),
                               "pgtos": evs.filter(event_type="S-1210").exists()})


# ------------------------------------------------------------------ manutenção
@transaction.atomic
def revalidate(ev: EsocialEvent, user=None) -> EsocialEvent:
    """Remonta o XML de evento ainda não exportado (após corrigir o cadastro)."""
    if ev.status not in (EventStatus.PENDENTE, EventStatus.VALIDADO):
        raise BusinessRuleError("Só eventos ainda não exportados podem ser remontados. Use 'Corrigir/retificar'.")
    if ev.event_type == "S-1299":
        raise BusinessRuleError("Gere um novo fechamento.")
    ctx = builders.Ctx.load(ev.institution).fresh()
    receipt = ev.replaces.receipt if ev.retification and ev.replaces_id else None
    extra = {"cad_ini": "<cadIni>S</cadIni>" in ev.xml}
    xml = _build(ctx, ev.event_type, _object(ev), ev.event_id, receipt, extra)
    ev.pendencies, ev.status = _finish(ctx, ev.event_type, xml)
    ev.xml = xml
    ev.save(update_fields=["xml", "pendencies", "status", "updated_at"])
    _log(ev, "REVALIDADO", f"{len(ev.pendencies)} pendência(s)", user)
    return ev


@transaction.atomic
def replace(ev: EsocialEvent, user=None) -> EsocialEvent:
    """Corrige evento rejeitado (novo envio) ou retifica evento aceito (indRetif=2 com o recibo original)."""
    if ev.status not in (EventStatus.REJEITADO, EventStatus.ACEITO):
        raise BusinessRuleError("Só eventos rejeitados ou aceitos podem ser corrigidos/retificados.")
    if ev.event_type in ("S-1010", "S-1299") and ev.status == EventStatus.ACEITO:
        raise BusinessRuleError("Para alterar rubrica aceita, crie nova versão da rubrica; o fechamento não se retifica.")
    if ev.replaced_by.exists():
        raise BusinessRuleError("Este evento já foi substituído.")
    extra = {"cad_ini": "<cadIni>S</cadIni>" in ev.xml}
    if ev.event_type == "S-1299":
        extra.update({"period": ev.period, "remun": "<evtRemun>S" in ev.xml, "pgtos": "<evtPgtos>S" in ev.xml})
    new = create_event(ev.institution, ev.event_type, obj=_object(ev), object_type=ev.object_type,
                       object_id=ev.object_id, reference=ev.reference, period=ev.period, cpf=ev.cpf, replaces=ev,
                       user=user, extra=extra)
    if ev.status == EventStatus.REJEITADO:
        ev.status = EventStatus.SUBSTITUIDO
        ev.save(update_fields=["status", "updated_at"])
    _log(ev, "SUBSTITUIDO", f"Novo evento {new.event_id}", user)
    return new


@transaction.atomic
def export(events: list[EsocialEvent], user=None) -> bytes:
    """ZIP com os XMLs (não assinados) para assinatura e transmissão. Eventos com pendência são recusados."""
    bad = [e for e in events if e.status not in (EventStatus.VALIDADO, EventStatus.EXPORTADO)]
    if bad:
        raise BusinessRuleError(f"{len(bad)} evento(s) com pendências ou já finalizados não podem ser exportados.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in events:
            z.writestr(f"{e.event_type}/{e.event_id}.xml", e.xml)
            if e.status == EventStatus.VALIDADO:
                e.status, e.exported_at = EventStatus.EXPORTADO, timezone.now()
                e.save(update_fields=["status", "exported_at", "updated_at"])
            _log(e, "EXPORTADO", "", user)
    log_event("EXPORT", module="esocial.eventos", object_repr=f"Exportação de {len(events)} evento(s) eSocial")
    return buf.getvalue()


@transaction.atomic
def register_return(ev: EsocialEvent, *, accepted: bool, receipt: str = "", code: str = "", message: str = "",
                    user=None) -> EsocialEvent:
    if ev.status != EventStatus.EXPORTADO:
        raise BusinessRuleError("Registre o retorno apenas de eventos exportados (aguardando retorno).")
    if accepted and not receipt.strip():
        raise BusinessRuleError("Informe o número do recibo do eSocial.")
    if not accepted and not (code.strip() or message.strip()):
        raise BusinessRuleError("Informe o código ou a mensagem de erro do eSocial.")
    ev.status = EventStatus.ACEITO if accepted else EventStatus.REJEITADO
    ev.receipt, ev.return_code, ev.return_message = receipt.strip(), code.strip(), message.strip()
    ev.returned_at = timezone.now()
    ev.save(update_fields=["status", "receipt", "return_code", "return_message", "returned_at", "updated_at"])
    _log(ev, "ACEITO" if accepted else "REJEITADO", receipt or f"{code} {message}", user)
    if accepted and ev.replaces_id:
        old = ev.replaces
        if old.status == EventStatus.ACEITO:
            old.status = EventStatus.SUBSTITUIDO
            old.save(update_fields=["status", "updated_at"])
    return ev


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def import_returns(institution, content: bytes, user=None) -> dict:
    """Lê o XML de retorno do processamento do lote (retornoProcessamentoLoteEventos) e registra os retornos."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise BusinessRuleError("Arquivo de retorno não é um XML válido.")
    return apply_returns(institution, root, user)


def _return_nodes(root):
    """Retorno de cada evento: <evento Id> de retornoEventos (consulta do lote) ou <retornoEvento Id> (arquivo)."""
    wrapped = [n for n in root.iter() if _local(n.tag) == "evento" and n.get("Id")
               and any(_local(x.tag) == "retornoEvento" for x in n.iter())]
    return wrapped or [n for n in root.iter() if _local(n.tag) == "retornoEvento" and n.get("Id")]


def apply_returns(institution, root, user=None) -> dict:
    found, done, missing = 0, 0, []
    for node in _return_nodes(root):
        found += 1
        vals = {}
        msgs = []
        for sub in node.iter():
            name = _local(sub.tag)
            if name in ("cdResposta", "descResposta", "nrRecibo") and sub.text:
                vals.setdefault(name, sub.text.strip())
            if name == "ocorrencia":
                parts = {_local(x.tag): (x.text or "").strip() for x in sub}
                msgs.append(f"{parts.get('codigo', '')} {parts.get('descricao', '')}".strip())
        ev = EsocialEvent.objects.filter(institution=institution, event_id=node.get("Id")).first()
        if ev is None or ev.status != EventStatus.EXPORTADO:
            missing.append(node.get("Id"))
            continue
        code = vals.get("cdResposta", "")
        ok = code in ("201", "202") and bool(vals.get("nrRecibo"))
        register_return(ev, accepted=ok, receipt=vals.get("nrRecibo", "") if ok else "", code=code,
                        message="; ".join([vals.get("descResposta", "")] + msgs).strip("; ") or "Sem mensagem",
                        user=user)
        done += 1
    if not found:
        raise BusinessRuleError("Nenhum 'retornoEvento' encontrado no arquivo.")
    return {"eventos_no_arquivo": found, "registrados": done, "nao_localizados": missing}


def summary(institution) -> dict:
    from django.db.models import Count

    rows = (EsocialEvent.objects.filter(institution=institution).values("event_type", "status")
            .annotate(n=Count("id")))
    out: dict = {t: {s: 0 for s in EventStatus.values} for t in EventType.values}
    for r in rows:
        out[r["event_type"]][r["status"]] = r["n"]
    return out

