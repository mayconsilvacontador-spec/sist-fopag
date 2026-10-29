"""
Processo DIGITALIZADO → benefício na folha, sem redigitar.

Etapa 1 — organizar a leitura: juntar leituras do mesmo processo (`merge`), acrescentar PDFs (`add_files`) e
escolher a pessoa quando os documentos não trazem CPF (`set_person`). Depois a leitura é aplicada normalmente
(pessoa, vínculo, averbações e todos os PDFs na Pasta do Servidor — `services.apply`).

Etapa 2 — implantar APOSENTADORIA JÁ CONCEDIDA (`implant`): com a leitura aplicada, registra a concessão como
concluída em processo anterior (ato, publicação, fundamentação, valor), cria o processo no Protocolo (concluído,
com o nº do processo original), implanta o benefício na folha com "pago pelo sistema anterior até" (sem retroativo
indevido), encerra o vínculo como APOSENTADO e deixa a concessão pronta para a Ficha FATIMA/SalContr.txt e para o
COMPREV (averbações com `comprev`). A trilha registra que veio de processo digitalizado. Nada passa de novo por
Jurídico/Controle/Presidência: o ato já existe e está nos documentos.
"""
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from . import reader
from .models import FileStatus, JobStatus, ReadingFile, ReadingJob
from .services import MAX_FILES, MODULE, _date, _money, _norm, documents, run_checks

OPEN = (JobStatus.LENDO, JobStatus.CONFERENCIA)


# ================================================================== etapa 1 — organizar a leitura
@transaction.atomic
def merge(target: ReadingJob, sources: list[ReadingJob], user) -> ReadingJob:
    """Leva os arquivos (com o que já foi lido e conferido) das outras leituras para esta. Nada é lido de novo."""
    target = ReadingJob.objects.select_for_update().get(pk=target.pk)
    if target.status not in OPEN:
        raise BusinessRuleError("Só é possível juntar em uma leitura que ainda está em leitura ou conferência.")
    sources = [s for s in sources if s.pk != target.pk]
    if not sources:
        raise BusinessRuleError("Escolha ao menos outra leitura para juntar.")
    order = target.files.count()
    if order + sum(s.files.count() for s in sources) > MAX_FILES:
        raise BusinessRuleError(f"Uma leitura comporta no máximo {MAX_FILES} arquivos.")
    for s in sources:
        if s.institution_id != target.institution_id or s.status not in OPEN:
            raise BusinessRuleError(f"A leitura \"{s.title}\" já foi aplicada ou descartada e não pode ser juntada.")
        if s.person_id and target.person_id and s.person_id != target.person_id:
            raise BusinessRuleError(f"A leitura \"{s.title}\" está ligada a outra pessoa.")
        for f in s.files.order_by("order"):
            f.job, f.order = target, order
            f.save(update_fields=["job", "order", "updated_at"])
            order += 1
        if s.person_id and not target.person_id:
            target.person_id = s.person_id
        s.status = JobStatus.DESCARTADO
        s.title = f"{s.title} (juntada em: {target.title})"[:200]
        s.save(update_fields=["status", "title", "updated_at"])
    _refresh(target)
    log_event("UPDATE", module=MODULE, obj=target, object_repr=f"Leituras juntadas em {target.title}",
              extra={"juntadas": [s.title for s in sources]})
    return target


@transaction.atomic
def add_files(job: ReadingJob, files) -> ReadingJob:
    if job.status not in OPEN:
        raise BusinessRuleError("Só é possível acrescentar arquivos a uma leitura em leitura ou conferência.")
    if not files:
        raise BusinessRuleError("Escolha os PDFs.")
    order = job.files.count()
    if order + len(files) > MAX_FILES:
        raise BusinessRuleError(f"Uma leitura comporta no máximo {MAX_FILES} arquivos.")
    for i, f in enumerate(sorted(files, key=lambda x: x.name or "")):
        data = f.read()
        if not data.startswith(b"%PDF"):
            raise BusinessRuleError(f"{f.name}: não é um PDF válido.")
        if len(data) > reader.MAX_BYTES:
            raise BusinessRuleError(f"{f.name}: acima de 30 MB, divida o arquivo.")
        rf = ReadingFile(institution=job.institution, job=job, file_name=(f.name or "documento.pdf")[:255],
                         file_size=len(data), sha256=hashlib.sha256(data).hexdigest(), order=order + i)
        rf.file.save(f"{rf.sha256[:16]}.pdf", ContentFile(data), save=False)
        rf.save()
    job.status = JobStatus.LENDO
    job.save(update_fields=["status", "updated_at"])
    log_event("UPDATE", module=MODULE, obj=job, object_repr=f"Arquivos acrescentados à leitura {job.title}",
              extra={"arquivos": len(files)})
    return job


@transaction.atomic
def set_person(job: ReadingJob, person) -> ReadingJob:
    if job.status not in OPEN:
        raise BusinessRuleError("A pessoa só pode ser escolhida antes de aplicar a leitura.")
    if person is not None and person.institution_id != job.institution_id:
        raise BusinessRuleError("Pessoa de outra instituição.")
    job.person = person
    job.save(update_fields=["person", "updated_at"])
    _refresh(job)
    return job


def _refresh(job: ReadingJob):
    if job.files.filter(status=FileStatus.PENDENTE).exists():
        job.status = JobStatus.LENDO
    else:
        job.status, job.checks = JobStatus.CONFERENCIA, run_checks(job)
    job.save(update_fields=["status", "checks", "updated_at"])


# ================================================================== etapa 2 — implantar benefício já concedido
def _all(job, key):
    """Valores conferidos de um campo, na ordem dos documentos (com o documento de origem)."""
    for rf, d in documents(job):
        for c in d.get("campos", []):
            if c["chave"] == key and not c["ignorado"] and c["valor"]:
                yield d, c["valor"]


def _first(job, key) -> str:
    return next((v for _, v in _all(job, key)), "")


def _guess_modality(text: str):
    t = _norm(text)
    for words, code in ((("INVALIDEZ", "INCAPACIDADE"), 4), (("COMPULSORIA",), 3), (("PROFESSOR", "MAGISTERIO"), 5),
                        (("ESPECIAL", "INSALUBR", "NOCIVO"), 7), (("TEMPO DE CONTRIBUICAO", "TEMPO DE SERVICO"), 2),
                        (("IDADE",), 1)):
        if any(w in t for w in words):
            return code
    return None


def _yes(v: str):
    t = _norm(v)
    return True if t.startswith(("SIM", "COM ", "S")) else False if t.startswith(("NAO", "SEM", "N")) else None


def prefill(job: ReadingJob) -> dict:
    """Sugestões para o formulário de implantação, tiradas do que foi lido e conferido."""
    from apps.employment.models import EmploymentLink
    from apps.institutions.models import PayrollGroup

    texto = " ".join(v for k in ("ato.tipo_beneficio", "ato.fundamentacao", "calculo.fundamentacao",
                                 "requerimento.beneficio", "requerimento.regra_pedida") for _, v in _all(job, k))
    # valor: contracheque de inativo mais recente; senão o do ato; senão o da memória de cálculo
    cheques = []
    for d, _ in _all(job, "contracheque.total_proventos"):
        get = {c["chave"]: c["valor"] for c in d["campos"] if not c["ignorado"]}
        if "INATIV" in _norm(get.get("contracheque.situacao", "")) or "APOSENT" in _norm(d.get("titulo", "")):
            cheques.append((get.get("contracheque.competencia", ""), get.get("contracheque.total_proventos", "")))
    cheques.sort(key=lambda x: _comp_key(x[0]), reverse=True)
    valor, origem = "", ""
    if cheques and _money(cheques[0][1]) is not None:
        valor, origem = cheques[0][1], f"contracheque de inativo {cheques[0][0]}".strip()
    elif _money(_first(job, "ato.valor_proventos")) is not None:
        valor, origem = _first(job, "ato.valor_proventos"), "valor do ato de concessão (confira reajustes)"
    elif _money(_first(job, "calculo.valor_total")) is not None:
        valor, origem = _first(job, "calculo.valor_total"), "memória de cálculo (confira reajustes)"
    links = []
    if job.person_id:
        links = [{"id": str(lk.pk), "rotulo": f"{lk.registration} · {lk.position.name} · {lk.organ.name} ({lk.get_status_display()})",
                  "massa": lk.segment} for lk in EmploymentLink.objects.filter(person=job.person).select_related("position", "organ")]
    massa = links[0]["massa"] if links else "PREVIDENCIARIO"
    grupos = [{"id": str(g.pk), "rotulo": f"{g.code} — {g.name}", "massa": g.segment}
              for g in PayrollGroup.objects.filter(institution=job.institution, active=True).order_by("code")]
    hoje = timezone.localdate()
    ultimo = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
    ato_data = _date(_first(job, "ato.data"))
    pub = _date(_first(job, "publicacao.data"))
    return {
        "pessoa": job.person.name if job.person_id else "", "vinculos": links, "folhas": grupos,
        "sugestao": {
            "tipo": "PENSAO" if any(d["tipo"] == "CERTIDAO_OBITO" for _, d in documents(job)) else "APOSENTADORIA",
            "vinculo": links[0]["id"] if links else "",
            "modalidade": _guess_modality(texto), "fundamentacao": _first(job, "ato.fundamentacao")
            or _first(job, "calculo.fundamentacao"),
            "ato_numero": _first(job, "ato.numero"), "ato_data": ato_data.isoformat() if ato_data else "",
            "publicacao_data": pub.isoformat() if pub else "", "publicacao_veiculo": _first(job, "publicacao.veiculo"),
            "inicio": (pub or ato_data).isoformat() if (pub or ato_data) else "",
            "requerimento_data": _first(job, "requerimento.data")[:10],
            "valor": str(_money(valor) or ""), "valor_origem": origem,
            "integralidade": _yes(_first(job, "ato.integralidade")), "paridade": _yes(_first(job, "ato.paridade")),
            "folha": next((g["id"] for g in grupos if g["massa"] == massa), grupos[0]["id"] if grupos else ""),
            "pago_ate": ultimo.isoformat()[:7], "processo_original": _first(job, "processo.numero"),
        },
    }


def _comp_key(txt: str):
    """Ordena competências escritas como 08/2025 ou 2025-08."""
    m = re.search(r"(\d{4})-(\d{1,2})", txt or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\D+(\d{4})", txt or "")
    return (int(m.group(2)), int(m.group(1))) if m else (0, 0)


def _dec(v, what) -> Decimal:
    try:
        x = Decimal(str(v).replace(".", "").replace(",", ".") if "," in str(v) else str(v))
    except InvalidOperation:
        raise BusinessRuleError(f"Valor inválido em {what}.")
    return x.quantize(Decimal("0.01"))


def _req_date(data, key, what, required=True):
    v = data.get(key)
    if not v:
        if required:
            raise BusinessRuleError(f"Informe {what}.")
        return None
    d = _date(v)
    if d is None:
        raise BusinessRuleError(f"Data inválida em {what}.")
    return d


@transaction.atomic
def implant(request, job: ReadingJob, data: dict) -> dict:
    from apps.concessao.models import (
        Benefit, BenefitEvent, BenefitEventKind, Concession, ConcessionStep, Modality, Parcel, StepAction, TceResult,
    )
    from apps.employment.models import EmploymentLink, EventType, FunctionalEvent
    from apps.institutions.models import PayrollGroup
    from apps.protocolo import services as proto
    from apps.protocolo.models import MovementKind, ProcessStatus, ProcessType, Sector

    job = ReadingJob.objects.select_for_update(of=("self",)).select_related("person").get(pk=job.pk)
    if job.status != JobStatus.APLICADO or not job.person_id:
        raise BusinessRuleError("Aplique a leitura à Pasta do Servidor antes de implantar o benefício.")
    if job.concession_id:
        raise BusinessRuleError("O benefício desta leitura já foi implantado.")
    inst, person, user = job.institution, job.person, request.user
    kind = data.get("tipo") or "APOSENTADORIA"
    if kind != "APOSENTADORIA":
        raise BusinessRuleError("Por enquanto a implantação de processo digitalizado é só de aposentadoria "
                                "(pensão por morte vem na próxima etapa).")
    modality = int(data.get("modalidade") or 0)
    if modality not in Modality.values:
        raise BusinessRuleError("Escolha a modalidade da aposentadoria.")
    legal_basis = str(data.get("fundamentacao") or "").strip()
    act_number = str(data.get("ato_numero") or "").strip()
    if not legal_basis or not act_number:
        raise BusinessRuleError("Informe a fundamentação e o número do ato de concessão.")
    act_date = _req_date(data, "ato_data", "a data do ato")
    pub_date = _req_date(data, "publicacao_data", "a data da publicação", required=False)
    start = _req_date(data, "inicio", "a data de início do benefício")
    req_date = _req_date(data, "requerimento_data", "a data do requerimento", required=False)
    amount = _dec(data.get("valor"), "o valor atual do benefício")
    if amount <= 0:
        raise BusinessRuleError("Informe o valor atual do benefício (o do contracheque mais recente).")
    group = PayrollGroup.objects.filter(institution=inst, pk=data.get("folha"), active=True).first()
    if group is None:
        raise BusinessRuleError("Escolha a folha (massa) do benefício.")
    pago = str(data.get("pago_ate") or "")
    m = re.fullmatch(r"(\d{4})-(\d{2})", pago[:7])
    if not m:
        raise BusinessRuleError("Informe até que mês o sistema anterior pagou o benefício.")
    paid_until = date(int(m.group(1)), int(m.group(2)), 1)
    if paid_until < start.replace(day=1):
        raise BusinessRuleError("\"Pago até\" não pode ser antes do início do benefício.")
    link = None
    if data.get("vinculo"):
        link = EmploymentLink.objects.filter(person=person, pk=data["vinculo"]).select_related("organ", "position").first()
        if link is None:
            raise BusinessRuleError("Vínculo inválido.")
    if Benefit.objects.filter(beneficiary=person, kind="APOSENTADORIA", status__in=["ATIVO", "SUSPENSO"]).exists():
        raise BusinessRuleError(f"{person.name} já tem aposentadoria ativa no sistema.")
    integral, parity = bool(data.get("integralidade")), bool(data.get("paridade"))

    # ---- processo no Protocolo (concluído), com o número do processo original
    ptype = ProcessType.objects.filter(institution=inst, name__iexact="APOSENTADORIA", active=True).first() or \
        ProcessType.objects.filter(institution=inst, active=True).first()
    mine = proto.user_sectors(user, inst)
    sector = (mine.filter(active=True).first() if hasattr(mine, "filter") else None) or \
        Sector.objects.filter(institution=inst, code="BEN", active=True).first() or \
        Sector.objects.filter(institution=inst, active=True).first()
    if ptype is None or sector is None:
        raise BusinessRuleError("Cadastre ao menos um tipo de processo e um setor no Protocolo.")
    original = str(data.get("processo_original") or "").strip()[:40]
    process = proto.open_process(
        request, process_type=ptype, sector=sector, interested=person, interested_name=person.name,
        subject=f"Aposentadoria concedida em processo anterior — implantação ({person.name})"[:255],
        description=f"Processo digitalizado lido pela Leitura inteligente ({job.title}). Ato {act_number}.",
        external_number=original)
    process.status, process.closed_at, process.pending_receipt = ProcessStatus.CONCLUIDO, timezone.now(), False
    process.save(update_fields=["status", "closed_at", "pending_receipt"])
    proto._move(process, MovementKind.CONCLUSAO, "Benefício já concedido; implantado no SIST a partir do processo "
                f"digitalizado (ato {act_number}).", from_sector=sector)

    # ---- concessão registrada como concluída
    tce = str(data.get("tce") or "")
    c = Concession.objects.create(
        institution=inst, process=process, kind="APOSENTADORIA", stage="IMPLANTADO", person=person, link=link,
        modality=modality, legal_basis=legal_basis[:255], local_legal_basis=str(data.get("legislacao_local") or "")[:255],
        request_date=req_date, validity_date=start, validity_class=1 if pub_date and pub_date == start else None,
        integralidade=integral, paridade=parity, total=amount, act_nature="PORTARIA", act_number=act_number[:30],
        act_date=act_date, publication_date=pub_date, publication_media=str(data.get("publicacao_veiculo") or "")[:150],
        implanted_at=timezone.now(),
        tce_sent_date=_req_date(data, "tce_envio", "a data de envio ao TCE", required=False) if tce else None,
        tce_reference=str(data.get("tce_processo") or "")[:60] if tce else "",
        tce_result=tce if tce in TceResult.values else "",
        tce_result_date=_req_date(data, "tce_julgamento", "a data do julgamento", required=False) if tce in TceResult.values else None,
        analysis={"origem": "PROCESSO_DIGITALIZADO", "leitura": str(job.pk), "processo_original": original},
        calculation={"forma": "Valor do benefício concedido em processo anterior (processo digitalizado)",
                     "valor_origem": str(data.get("valor_origem") or ""), "avisos": []},
    )
    Parcel.objects.create(institution=inst, concession=c, kind="PROVENTO", name="Proventos (valor atual)",
                          amount=amount, correlation="Vencimento" if integral else "Média", legal_basis=legal_basis[:100])
    ConcessionStep.objects.create(
        institution=inst, concession=c, action=StepAction.IMPLANTACAO, role="IMPLANTACAO", stage_from="",
        stage_to="IMPLANTADO", user=user, signed=False,
        text=f"Aposentadoria concedida em processo anterior (ato {act_number} de {act_date:%d/%m/%Y}). Implantada a "
             f"partir do processo digitalizado, com os dados conferidos pela equipe na Leitura inteligente.",
        data={"leitura": str(job.pk), "pago_ate": paid_until.isoformat(), "valor": str(amount)})

    # ---- benefício na folha (sem retroativo do que o sistema anterior já pagou)
    b = Benefit.objects.create(
        institution=inst, kind="APOSENTADORIA", modality=modality, beneficiary=person, concession=c,
        payroll_group=group, registration=(link.registration if link else "")[:30], legal_basis=legal_basis[:255],
        start_date=start, amount=amount, integralidade=integral, paridade=parity, paid_until=paid_until)
    BenefitEvent.objects.create(institution=inst, benefit=b, kind=BenefitEventKind.IMPLANTACAO, date=start, act=act_number[:100],
                                justification=f"Implantação de aposentadoria concedida em processo anterior (digitalizado). "
                                              f"Pago pelo sistema anterior até {paid_until:%m/%Y}.",
                                new_values={"valor": str(amount), "folha": group.code}, process=process)

    # ---- vínculo encerrado como aposentado
    if link is not None and link.status == "ATIVO":
        link.status, link.end_date = "APOSENTADO", start - timedelta(days=1)
        link.end_reason = f"Aposentadoria — {act_number}"[:255]
        link.save(update_fields=["status", "end_date", "end_reason", "updated_at"])
        FunctionalEvent.objects.create(institution=inst, link=link, event_type=EventType.APOSENTADORIA, start_date=start,
                                       act_type="PORTARIA", act_number=act_number[:30], act_date=act_date,
                                       publication=str(data.get("publicacao_veiculo") or "")[:120],
                                       description=f"Aposentadoria ({c.get_modality_display()}) — {legal_basis[:200]}")

    job.concession = c
    job.save(update_fields=["concession", "updated_at"])
    log_event("CREATE", module="concessao.implantacao", obj=c,
              object_repr=f"Aposentadoria implantada a partir de processo digitalizado — {person.name}",
              extra={"processo": process.code, "valor": str(amount), "folha": group.code, "pago_ate": paid_until.isoformat()})

    from apps.previdencia.models import Averbacao
    comprev = Averbacao.objects.filter(person=person, active=True, comprev=True).count()
    avisos = []
    if link is None:
        avisos.append("Sem vínculo: a Ficha FATIMA sai sem órgão/matrícula — inclua o vínculo na Pasta do Servidor.")
    elif not link.organ.sigfis_code:
        avisos.append("O órgão do vínculo está sem código SIGFIS: preencha em Cadastros › Órgãos antes de gerar o SalContr.txt.")
    if not person.bank_accounts.filter(valid_to__isnull=True).exists():
        avisos.append("Sem conta bancária: cadastre na Pasta do Servidor antes de pagar a folha.")
    if not person.contribution_salaries.exists():
        avisos.append("Sem histórico de salários de contribuição: o SalContr.txt (FATIMA) precisa deles.")
    return {"concessao": str(c.pk), "processo": process.code, "beneficio": str(b.pk), "folha": group.code,
            "pago_ate": paid_until.strftime("%m/%Y"), "comprev_averbacoes": comprev,
            "tce": c.get_tce_result_display() if c.tce_result else ("enviado" if c.tce_sent_date else "a enviar"),
            "avisos": avisos}
