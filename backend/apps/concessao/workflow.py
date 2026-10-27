"""
Fluxo de decisão da concessão — mapeamento da PREVIBAM (MM-APOSVOL, MM-APOSCOMP, MM-APOSINV, MM-PENSAO,
MM-REVEBENEF):

  Benefícios (instrução) → Jurídico (parecer) → Controle Interno (conformidade) → Presidência (assina a portaria)
  → publicação → Folha (implantação) → envio ao TCE-RJ → julgamento (legal / ressalva / ilegal → anulação)

Na revisão não há etapa de Controle Interno (Jurídico → Presidência).

Salvaguardas (o sistema NUNCA concede nem implanta com um clique):
1. Cada etapa exige permissão própria (concessao.juridico, .controle_interno, .presidencia, .implantacao, .tce).
2. Segregação de funções: a mesma pessoa não pode instruir, dar parecer, conferir e assinar o mesmo processo;
   quem instruiu não implanta. Parâmetro 'concessao.segregacao_funcoes' (padrão: ativo).
3. Assinatura eletrônica: parecer, conformidade, assinatura, indeferimento, implantação e anulação exigem a senha
   do usuário; cada ato gera hash SHA-256 na trilha (ConcessionStep), que nunca é alterada.
4. Na assinatura os valores ficam fixados (snapshot com hash). A implantação confere o hash: se algo mudou depois
   da assinatura, a implantação é recusada.
5. Minuta (após o parecer favorável), portaria (na assinatura), ofício de indeferimento e minuta de anulação são
   gerados em Word, anexados ao processo do Protocolo e avisados ao setor de Benefícios na Central de Alertas.
6. Processo digital (checklist.py): cada setor só libera o processo com os documentos obrigatórios do seu checklist
   anexados (ou justificados); o ato com senha assina o checklist com SHA-256, registrado na trilha e no Protocolo.
"""
import hashlib
import json
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from . import checklist, documents
from .models import (
    STEP_ROLE, Concession, ConcessionKind, ConcessionStep, DocumentKind, Stage, StepAction, TceResult,
)

SEGREGATION_PARAM = "concessao.segregacao_funcoes"
ROLE_LABEL = {"INSTRUCAO": "instrução (Benefícios)", "JURIDICO": "parecer jurídico", "CONTROLE": "Controle Interno",
              "PRESIDENCIA": "Presidência", "IMPLANTACAO": "implantação (Folha)"}
# Papéis que não podem ser acumulados pela mesma pessoa no mesmo processo
CONFLICTS = {
    "JURIDICO": {"INSTRUCAO"},
    "CONTROLE": {"INSTRUCAO", "JURIDICO"},
    "PRESIDENCIA": {"INSTRUCAO", "JURIDICO", "CONTROLE"},
    "IMPLANTACAO": {"INSTRUCAO"},
}


# ------------------------------------------------------------------ salvaguardas
def confirm_password(user, password: str):
    """Assinatura eletrônica: confirma a identidade com a senha antes de um ato decisivo."""
    from apps.accounts import services as acc

    if not password:
        raise BusinessRuleError("Confirme o ato com a sua senha (assinatura eletrônica).")
    if not user.check_password(password):
        acc.register_login_failure(user, user.username, "senha_incorreta_assinatura")
        raise BusinessRuleError("Senha incorreta. O ato NÃO foi registrado.")


def _segregation_on(institution) -> bool:
    from apps.institutions.services import get_parameter

    v = get_parameter(institution, SEGREGATION_PARAM, default=True)
    return str(v).lower() not in ("false", "0", "nao", "não")


def check_segregation(c: Concession, user, role: str):
    if not _segregation_on(c.institution):
        return
    acted = set(c.steps.filter(user=user).exclude(role="").values_list("role", flat=True))
    clash = acted & CONFLICTS.get(role, set())
    if clash:
        done = ", ".join(ROLE_LABEL[r] for r in sorted(clash))
        raise BusinessRuleError(
            f"Segregação de funções: você já atuou neste processo na etapa de {done} e não pode praticar o ato de "
            f"{ROLE_LABEL[role]}. Outra pessoa do setor competente deve fazê-lo.")


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def record(c: Concession, user, action: str, *, stage_from="", text="", data=None, signed=False) -> ConcessionStep:
    payload = {"concession": str(c.pk), "action": action, "user": str(user.pk), "at": timezone.now().isoformat(),
               "stage_from": stage_from, "stage_to": c.stage, "text": text, "data": data or {},
               "valores": c.signed_snapshot or {"total": str(c.total or "")}}
    step = ConcessionStep.objects.create(
        institution=c.institution, concession=c, action=action, role=STEP_ROLE.get(action, ""), stage_from=stage_from,
        stage_to=c.stage, user=user, text=text, data=data or {}, signed=signed,
        signature_hash=_hash(payload) if signed else "")
    log_event("UPDATE", module="concessao.processos", obj=c, object_repr=f"Concessão — {StepAction(action).label}",
              user=user, extra={"etapa": c.stage, "assinado": signed, "hash": step.signature_hash or None})
    return step


def _move(c: Concession, text: str, sector=None):
    """Andamento no processo do Protocolo (tramitação documentada)."""
    from apps.protocolo.models import Movement, MovementKind

    Movement.objects.create(institution=c.institution, process=c.process, kind=MovementKind.DESPACHO,
                            from_sector=c.process.current_sector, occurred_at=timezone.now(), text=text[:2000],
                            due_date_after=c.process.due_date)


def _notify(c: Concession):
    """Atualiza a Central de Alertas (pendências por setor e documentos disponíveis)."""
    from apps.alerts.services import run_checks

    try:
        run_checks(c.institution)
    except Exception:  # a falha de alerta não pode desfazer um ato válido
        pass


def _require(c: Concession, *stages):
    if c.stage not in stages:
        allowed = ", ".join(Stage(s).label.lower() for s in stages)
        raise BusinessRuleError(f"Ato não permitido na etapa '{c.get_stage_display()}'. Etapa exigida: {allowed}.")


def _min_text(text: str, n: int, what: str) -> str:
    if not text or len(text.strip()) < n:
        raise BusinessRuleError(f"Registre {what} (mínimo de {n} caracteres).")
    return text.strip()


def snapshot(c: Concession) -> dict:
    """Valores que a assinatura fixa — a implantação confere que nada mudou."""
    return {
        "tipo": c.kind, "pessoa": str(c.person_id), "regra": c.rule.code if c.rule_id else "",
        "modalidade": c.modality, "data_validade": c.validity_date.isoformat() if c.validity_date else "",
        "total": str(c.total or ""), "integralidade": c.integralidade, "paridade": c.paridade,
        "parcelas": [[p.kind, p.name, str(p.amount)] for p in c.parcels.order_by("kind", "id")],
        "cotas": [[str(q.dependent_id), str(q.percent), str(q.amount), q.duration,
                   q.end_date.isoformat() if q.end_date else ""] for q in c.quotas.order_by("dependent_id")],
        "beneficio_revisto": str(c.revised_benefit_id or ""),
    }


# ------------------------------------------------------------------ etapas
@transaction.atomic
def _sector_docs(c: Concession, user, sector: str, kind: str | None = None) -> dict:
    """Gera o documento do setor (se houver), liga ao checklist e assina o checklist (SHA-256 no Protocolo)."""
    if kind:
        doc = documents.generate(c, kind)
        checklist.fulfil_system(c, sector, doc, user)
    return checklist.seal(c, sector, user)


@transaction.atomic
def send_to_legal(c: Concession, user, *, acknowledge_warnings: bool = False, password: str = "") -> Concession:
    """
    Benefícios libera o processo: checklist completo (documentos anexados ou justificados), ciência dos avisos do
    cálculo e senha. Gera o relatório de instrução e assina o checklist (código SHA-256 no processo digital).
    """
    _require(c, Stage.CALCULADO)
    if not c.total:
        raise BusinessRuleError("Calcule os proventos antes de enviar ao Jurídico.")
    warnings = list((c.calculation or {}).get("avisos") or [])
    if warnings and not acknowledge_warnings:
        raise BusinessRuleError("O cálculo tem avisos. Confira cada um e confirme a ciência antes de enviar ao "
                                "Jurídico: " + " | ".join(warnings))
    checklist.require_complete(c, "BENEFICIOS")
    confirm_password(user, password)
    seal = _sector_docs(c, user, "BENEFICIOS", DocumentKind.RELATORIO_INSTRUCAO)
    prev = c.stage
    c.stage = Stage.ANALISE_JURIDICA
    c.save(update_fields=["stage", "updated_at"])
    data = {"checklist": seal}
    if warnings:
        data["avisos_cientes"] = warnings
    record(c, user, StepAction.ENVIO_JURIDICO, stage_from=prev, signed=True, data=data,
           text=("Ciente dos avisos do cálculo: " + " | ".join(warnings)) if warnings else "")
    _move(c, "Processo instruído (enquadramento, tempo e cálculo) e encaminhado à Procuradoria Jurídica para parecer.")
    _notify(c)
    return c


@transaction.atomic
def legal_opinion(c: Concession, user, *, favorable: bool, text: str, password: str) -> Concession:
    _require(c, Stage.ANALISE_JURIDICA)
    check_segregation(c, user, "JURIDICO")
    text = _min_text(text, 30, "o parecer jurídico")
    if favorable:
        checklist.require_complete(c, "JURIDICO")
    confirm_password(user, password)
    prev = c.stage
    if favorable:
        c.opinion = text
        c.save(update_fields=["opinion", "updated_at"])
        seal = _sector_docs(c, user, "JURIDICO", DocumentKind.PARECER_JURIDICO)
        c.stage = Stage.PRESIDENCIA if c.kind == ConcessionKind.REVISAO else Stage.CONTROLE_INTERNO
        c.save(update_fields=["stage", "updated_at"])
        record(c, user, StepAction.PARECER_FAVORAVEL, stage_from=prev, text=text, signed=True, data={"checklist": seal})
        doc = documents.generate(c, DocumentKind.MINUTA_PORTARIA)
        record(c, user, StepAction.DOCUMENTO, stage_from=c.stage, data={"documento": doc.file_name, "sha256": doc.sha256})
        _move(c, f"Parecer jurídico FAVORÁVEL. Minuta de portaria gerada e anexada ({doc.file_name}). "
                 f"Encaminhado {'à Presidência' if c.stage == Stage.PRESIDENCIA else 'ao Controle Interno'}.")
    else:
        c.stage, c.returned_count = Stage.CALCULADO, c.returned_count + 1
        c.save(update_fields=["stage", "returned_count", "updated_at"])
        record(c, user, StepAction.DEVOLUCAO_JURIDICO, stage_from=prev, text=text, signed=True)
        _move(c, f"Parecer jurídico pela DEVOLUÇÃO ao setor de Benefícios para correções: {text}")
    _notify(c)
    return c


@transaction.atomic
def compliance(c: Concession, user, *, conform: bool, text: str, password: str) -> Concession:
    _require(c, Stage.CONTROLE_INTERNO)
    check_segregation(c, user, "CONTROLE")
    text = _min_text(text, 20, "a análise de conformidade")
    if conform:
        checklist.require_complete(c, "CONTROLE")
    confirm_password(user, password)
    prev = c.stage
    c.compliance_opinion = text
    if conform:
        c.save(update_fields=["compliance_opinion", "updated_at"])
        seal = _sector_docs(c, user, "CONTROLE", DocumentKind.PARECER_CONTROLE)
        c.stage = Stage.PRESIDENCIA
        c.save(update_fields=["stage", "updated_at"])
        record(c, user, StepAction.CONFORMIDADE, stage_from=prev, text=text, signed=True, data={"checklist": seal})
        _move(c, "Controle Interno: CONFORME (regras aplicadas e memória de cálculo). Encaminhado à Presidência.")
    else:
        c.stage, c.returned_count = Stage.CALCULADO, c.returned_count + 1
        c.save(update_fields=["compliance_opinion", "stage", "returned_count", "updated_at"])
        record(c, user, StepAction.DEVOLUCAO_CONTROLE, stage_from=prev, text=text, signed=True)
        _move(c, f"Controle Interno: NÃO CONFORME — devolvido ao setor de Benefícios: {text}")
    _notify(c)
    return c


@transaction.atomic
def sign(c: Concession, user, *, nature: str, number: str, act_date: date, password: str) -> Concession:
    """Presidência assina a portaria: fixa os valores (snapshot + hash) e gera a portaria numerada."""
    _require(c, Stage.PRESIDENCIA)
    check_segregation(c, user, "PRESIDENCIA")
    if not number.strip():
        raise BusinessRuleError("Informe o número da portaria.")
    if act_date > timezone.localdate():
        raise BusinessRuleError("A data da portaria não pode ser futura.")
    if Concession.objects.filter(institution=c.institution, act_nature=nature, act_number=number.strip(),
                                 act_date__year=act_date.year).exclude(pk=c.pk).exists():
        raise BusinessRuleError(f"Já existe ato {nature} nº {number} em {act_date.year}.")
    checklist.require_complete(c, "PRESIDENCIA")
    confirm_password(user, password)
    prev = c.stage
    c.act_nature, c.act_number, c.act_date = nature, number.strip(), act_date
    c.approved_by, c.approved_at = user, timezone.now()
    c.signed_snapshot = snapshot(c)
    c.signed_hash = _hash(c.signed_snapshot)
    c.save()
    doc = documents.generate(c, DocumentKind.PORTARIA, number=c.act_number, act_date=act_date)
    checklist.fulfil_system(c, "PRESIDENCIA", doc, user)
    seal = checklist.seal(c, "PRESIDENCIA", user)
    c.stage = Stage.ATO_EMITIDO
    c.save(update_fields=["stage", "updated_at"])
    record(c, user, StepAction.ASSINATURA, stage_from=prev, signed=True,
           data={"ato": f"{nature} {number}", "data": act_date.isoformat(), "hash_valores": c.signed_hash,
                 "checklist": seal})
    record(c, user, StepAction.DOCUMENTO, stage_from=c.stage, data={"documento": doc.file_name, "sha256": doc.sha256})
    _move(c, f"Portaria {c.act_number} assinada pela Presidência em {act_date:%d/%m/%Y}. Documento anexado "
             f"({doc.file_name}). Encaminhar para publicação.")
    _notify(c)
    return c


@transaction.atomic
def reject(c: Concession, user, *, reason: str, password: str) -> Concession:
    _require(c, Stage.INSTRUCAO, Stage.ENQUADRADO, Stage.CALCULADO, Stage.ANALISE_JURIDICA, Stage.CONTROLE_INTERNO,
             Stage.PRESIDENCIA)
    check_segregation(c, user, "PRESIDENCIA")
    reason = _min_text(reason, 30, "o fundamento do indeferimento")
    confirm_password(user, password)
    prev = c.stage
    c.stage, c.rejection_reason = Stage.INDEFERIDO, reason
    c.save(update_fields=["stage", "rejection_reason", "updated_at"])
    record(c, user, StepAction.INDEFERIMENTO, stage_from=prev, text=reason, signed=True)
    doc = documents.generate(c, DocumentKind.CIENCIA_INDEFERIMENTO, reason=reason)
    record(c, user, StepAction.DOCUMENTO, stage_from=c.stage, data={"documento": doc.file_name, "sha256": doc.sha256})
    _move(c, f"Requerimento INDEFERIDO pela Presidência. Ofício de ciência anexado ({doc.file_name}): {reason}")
    _notify(c)
    return c


@transaction.atomic
def publish(c: Concession, user, *, publication_date: date, media: str, password: str = "") -> Concession:
    """Folha registra a publicação: exige a cópia da publicação no checklist e senha (assina o checklist da Folha)."""
    _require(c, Stage.ATO_EMITIDO)
    if publication_date < c.act_date:
        raise BusinessRuleError("A publicação não pode ser anterior à assinatura da portaria.")
    if publication_date > timezone.localdate():
        raise BusinessRuleError("A data de publicação não pode ser futura.")
    if not media or len(media.strip()) < 5:
        raise BusinessRuleError("Informe o meio de publicação (ex.: Notícia Oficial nº e data).")
    checklist.require_complete(c, "FOLHA")
    confirm_password(user, password)
    from .models import ValidityClass

    seal = checklist.seal(c, "FOLHA", user)
    prev = c.stage
    c.publication_date, c.publication_media, c.stage = publication_date, media.strip(), Stage.PUBLICADO
    if c.validity_class == ValidityClass.PUBLICACAO:
        c.validity_date = publication_date
        c.signed_snapshot = {**c.signed_snapshot, "data_validade": publication_date.isoformat()}
        c.signed_hash = _hash(c.signed_snapshot)
    c.save()
    record(c, user, StepAction.PUBLICACAO, stage_from=prev, signed=True,
           data={"data": publication_date.isoformat(), "meio": media, "checklist": seal})
    _move(c, f"Portaria publicada em {publication_date:%d/%m/%Y} ({media}). Pronta para implantação em folha.")
    _notify(c)
    return c


@transaction.atomic
def implant(c: Concession, user, *, password: str):
    """Folha de pagamento implanta — somente o que foi assinado, conferido pelo hash."""
    from . import services

    _require(c, Stage.PUBLICADO)
    check_segregation(c, user, "IMPLANTACAO")
    if not c.signed_hash or _hash(snapshot(c)) != c.signed_hash:
        raise BusinessRuleError("Os dados da concessão não conferem com os assinados pela Presidência. "
                                "A implantação foi bloqueada — verifique a trilha do processo.")
    confirm_password(user, password)
    prev = c.stage
    created = services.implant(c)
    record(c, user, StepAction.IMPLANTACAO, stage_from=prev, signed=True,
           data={"beneficios": [str(b.pk) for b in created], "hash_valores": c.signed_hash})
    _notify(c)
    return created


# ------------------------------------------------------------------ sobrestamento (pausa) e desistência
def _process_status(c: Concession, status: str, kind: str, text: str):
    """Reflete no processo do Protocolo (sobrestado/retomado/arquivado), com o andamento documentado."""
    from apps.protocolo import deadlines
    from apps.protocolo.models import Movement, ProcessStatus
    from apps.protocolo.services import holidays_for

    p = c.process
    today = timezone.localdate()
    if status == ProcessStatus.EM_TRAMITACAO and p.status == ProcessStatus.SOBRESTADO and p.suspended_since:
        # Os dias de sobrestamento não contam no prazo do processo
        hol = holidays_for(p.institution)
        paused = deadlines.count_days(p.suspended_since, today, p.business_days, hol)
        p.due_date = deadlines.add_days(p.due_date, paused, p.business_days, hol)
        if p.sector_due_date:
            p.sector_due_date = deadlines.add_days(p.sector_due_date, paused, p.business_days, hol)
        text += f"\nPrazo estendido em {paused} dia(s) de sobrestamento."
    if status == ProcessStatus.SOBRESTADO:
        p.suspended_since = p.suspended_since if p.status == ProcessStatus.SOBRESTADO else today
    else:
        p.suspended_since = None
    if status == ProcessStatus.ARQUIVADO:
        p.closed_at = timezone.now()
    p.status = status
    p.save()
    Movement.objects.create(institution=c.institution, process=p, kind=kind, from_sector=p.current_sector,
                            occurred_at=timezone.now(), text=text[:2000], due_date_after=p.due_date)


@transaction.atomic
def suspend(c: Concession, user, *, reason: str, until: date | None, password: str) -> Concession:
    """Pausa o processo (ex.: servidor pediu prazo, aguarda documento). Nada é perdido; a retomada volta à etapa."""
    from apps.protocolo.models import MovementKind, ProcessStatus

    from .models import PAUSABLE_STAGES

    if c.stage not in PAUSABLE_STAGES:
        raise BusinessRuleError("Só é possível sobrestar o processo antes da assinatura da portaria.")
    reason = _min_text(reason, 20, "o motivo do sobrestamento")
    if until and until < timezone.localdate():
        raise BusinessRuleError("A previsão de retomada não pode ser uma data passada.")
    confirm_password(user, password)
    prev = c.stage
    c.suspended_from, c.suspended_since, c.suspended_until = prev, timezone.localdate(), until
    c.suspension_reason, c.stage = reason, Stage.SOBRESTADO
    c.save()
    record(c, user, StepAction.SOBRESTAMENTO, stage_from=prev, text=reason, signed=True,
           data={"retomada_prevista": until.isoformat() if until else None})
    _process_status(c, ProcessStatus.SOBRESTADO, MovementKind.SOBRESTAMENTO,
                    f"Concessão sobrestada (pausada) na etapa '{Stage(prev).label}'"
                    + (f", com retomada prevista para {until:%d/%m/%Y}" if until else "") + f": {reason}")
    _notify(c)
    return c


@transaction.atomic
def resume(c: Concession, user, *, text: str, password: str) -> Concession:
    from apps.protocolo.models import MovementKind, ProcessStatus

    _require(c, Stage.SOBRESTADO)
    text = _min_text(text, 10, "o motivo da retomada")
    confirm_password(user, password)
    back = c.suspended_from or Stage.INSTRUCAO
    c.stage = back
    c.suspended_from, c.suspended_since, c.suspended_until = "", None, None
    c.save()
    record(c, user, StepAction.RETOMADA, stage_from=Stage.SOBRESTADO, text=text, signed=True)
    _process_status(c, ProcessStatus.EM_TRAMITACAO, MovementKind.RETOMADA,
                    f"Concessão retomada na etapa '{Stage(back).label}': {text}")
    _notify(c)
    return c


@transaction.atomic
def withdraw(c: Concession, user, *, reason: str, request_attached: bool, password: str) -> Concession:
    """
    Desistência do requerente: arquiva o processo sem concessão e gera o termo de desistência.
    Exige o pedido escrito do requerente juntado ao processo. Só antes da assinatura da portaria.
    """
    from apps.protocolo.models import MovementKind, ProcessStatus

    from .models import PAUSABLE_STAGES

    if c.stage not in PAUSABLE_STAGES + [Stage.SOBRESTADO]:
        raise BusinessRuleError("A desistência só pode ser registrada antes da assinatura da portaria. Depois dela, "
                                "a Presidência precisa tornar o ato sem efeito.")
    reason = _min_text(reason, 20, "o motivo da desistência")
    if not request_attached:
        raise BusinessRuleError("Junte ao processo o pedido de desistência assinado pelo requerente e confirme.")
    confirm_password(user, password)
    prev = c.stage
    c.stage, c.withdrawal_reason, c.withdrawn_at = Stage.DESISTENCIA, reason, timezone.now()
    c.suspended_from, c.suspended_until = "", None
    c.save()
    record(c, user, StepAction.DESISTENCIA, stage_from=prev, text=reason, signed=True,
           data={"pedido_juntado": True})
    doc = documents.generate(c, DocumentKind.TERMO_DESISTENCIA)
    record(c, user, StepAction.DOCUMENTO, stage_from=c.stage, data={"documento": doc.file_name, "sha256": doc.sha256})
    _process_status(c, ProcessStatus.ARQUIVADO, MovementKind.ARQUIVAMENTO,
                    f"Arquivado por DESISTÊNCIA do requerente ({reason}). Termo anexado ({doc.file_name}). "
                    "Nenhum benefício foi concedido; o vínculo permanece ativo.")
    _notify(c)
    return c


@transaction.atomic
def tce_send(c: Concession, user, *, sent_date: date, reference: str) -> Concession:
    _require(c, Stage.IMPLANTADO)
    c.tce_sent_date, c.tce_reference = sent_date, reference.strip()[:60]
    c.save(update_fields=["tce_sent_date", "tce_reference", "updated_at"])
    record(c, user, StepAction.ENVIO_TCE, stage_from=c.stage, data={"data": sent_date.isoformat(), "processo": reference})
    _move(c, f"Encaminhado ao TCE-RJ para registro/homologação em {sent_date:%d/%m/%Y} (processo {reference}).")
    _notify(c)
    return c


@transaction.atomic
def tce_judgment(c: Concession, user, *, result: str, result_date: date, notes: str) -> Concession:
    _require(c, Stage.IMPLANTADO)
    if not c.tce_sent_date:
        raise BusinessRuleError("Registre antes o envio ao TCE-RJ.")
    if result not in TceResult.values:
        raise BusinessRuleError("Resultado inválido.")
    c.tce_result, c.tce_result_date, c.tce_notes = result, result_date, notes.strip()
    c.save(update_fields=["tce_result", "tce_result_date", "tce_notes", "updated_at"])
    record(c, user, StepAction.JULGAMENTO_TCE, stage_from=c.stage, text=notes,
           data={"resultado": result, "data": result_date.isoformat()})
    if result == TceResult.ILEGAL:
        doc = documents.generate(c, DocumentKind.MINUTA_ANULACAO)
        record(c, user, StepAction.DOCUMENTO, stage_from=c.stage, data={"documento": doc.file_name, "sha256": doc.sha256})
        _move(c, f"TCE-RJ julgou ILEGAL a concessão. Minuta de portaria de anulação gerada ({doc.file_name}).")
    else:
        _move(c, f"TCE-RJ: {TceResult(result).label}. {notes}".strip())
    _notify(c)
    return c


@transaction.atomic
def annul(c: Concession, user, *, number: str, act_date: date, password: str) -> Concession:
    """Anulação após julgamento ILEGAL: cessa os benefícios; na aposentadoria, o vínculo volta a ativo."""
    from apps.employment.models import LinkStatus

    from .models import BenefitEventKind, BenefitStatus
    from .services import event

    _require(c, Stage.IMPLANTADO)
    if c.tce_result != TceResult.ILEGAL:
        raise BusinessRuleError("A anulação exige julgamento ILEGAL do TCE-RJ registrado.")
    check_segregation(c, user, "PRESIDENCIA")
    if not number.strip():
        raise BusinessRuleError("Informe o número da portaria de anulação.")
    confirm_password(user, password)
    act = f"Portaria nº {number.strip()} de {act_date:%d/%m/%Y} (anulação — julgamento do TCE-RJ)"
    for b in c.benefits.exclude(status=BenefitStatus.CESSADO):
        event(b, BenefitEventKind.CESSACAO, act_date, f"Anulação da concessão por decisão do TCE-RJ "
                                                      f"(processo {c.tce_reference}).", act=act[:100])
    if c.kind == ConcessionKind.APOSENTADORIA and c.link and c.link.status == LinkStatus.APOSENTADO:
        c.link.status, c.link.end_date, c.link.end_reason = LinkStatus.ATIVO, None, ""
        c.link.save()
    prev = c.stage
    c.stage, c.annulled_at, c.annulment_act = Stage.ANULADO, timezone.now(), act[:120]
    c.save(update_fields=["stage", "annulled_at", "annulment_act", "updated_at"])
    record(c, user, StepAction.ANULACAO, stage_from=prev, signed=True, data={"ato": act})
    doc = documents.generate(c, DocumentKind.PORTARIA_ANULACAO, number=number.strip(), act_date=act_date)
    record(c, user, StepAction.DOCUMENTO, stage_from=c.stage, data={"documento": doc.file_name, "sha256": doc.sha256})
    _move(c, f"Concessão ANULADA ({act}). Benefício excluído da folha"
             + ("; servidor deve retornar à folha dos ativos (comunicar RH)." if c.kind == ConcessionKind.APOSENTADORIA else "."))
    _notify(c)
    return c
