"""
Processo digital da concessão: checklist de documentos por setor.

- Cada tipo de processo (aposentadoria, pensão, revisão) tem uma lista de documentos por setor, editável pela
  instituição (ChecklistTemplate). A lista inicial é uma SUGESTÃO tirada dos manuais PREVIBAM (MM-APOSVOL,
  MM-APOSCOMP, MM-APOSINV, MM-PENSAO, MM-REVEBENEF), que citam os documentos de forma genérica — conferir.
- Documento "ANEXO": o setor anexa o arquivo (PDF/JPG/PNG); ele vai para o processo do Protocolo com SHA-256.
- Documento "SISTEMA": gerado pelo próprio sistema no ato do setor (relatório de instrução, parecer, portaria).
- Um setor só libera o processo (envio, parecer, conformidade, assinatura, publicação) com todos os itens
  obrigatórios do seu checklist cumpridos ou justificados como "não se aplica". O ato, confirmado com senha,
  ASSINA o checklist: o sistema calcula um código SHA-256 sobre os arquivos do setor e registra na trilha e no
  andamento do Protocolo (processo digital).
- Só o setor que está com o processo altera o seu checklist; depois de assinado, fica travado (volta a abrir se o
  processo for devolvido ao setor).
"""
import hashlib
import json

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import (
    SECTOR_BY_STAGE, ChecklistItem, ChecklistSector, ChecklistSource, ChecklistStatus, ChecklistTemplate,
    DocumentKind, Modality,
)

S, A = ChecklistSector, ChecklistSource

# (tipo, modalidade ou None, setor, documento, orientação, origem, documento do sistema, obrigatório)
DEFAULT_CHECKLIST = [
    # ---------------- aposentadoria (MM-APOSVOL / MM-APOSCOMP / MM-APOSINV)
    ("APOSENTADORIA", None, S.BENEFICIOS, "Requerimento de aposentadoria assinado pelo servidor", "", A.ANEXO, "", True),
    ("APOSENTADORIA", Modality.COMPULSORIA, S.BENEFICIOS, "Ofício do RH da PMBM notificando o alcance da idade-limite",
     "Na compulsória o processo começa pela notificação do RH (MM-APOSCOMP).", A.ANEXO, "", True),
    ("APOSENTADORIA", Modality.INCAPACIDADE, S.BENEFICIOS, "Laudo da junta médica oficial",
     "Laudo pericial que fundamenta a incapacidade permanente (MM-APOSINV).", A.ANEXO, "", True),
    ("APOSENTADORIA", None, S.BENEFICIOS, "Documento de identidade e CPF do servidor", "", A.ANEXO, "", True),
    ("APOSENTADORIA", None, S.BENEFICIOS, "Comprovante de residência", "", A.ANEXO, "", True),
    ("APOSENTADORIA", None, S.BENEFICIOS, "Pasta funcional / assentamentos funcionais (RH da PMBM)",
     "Documentação funcional fornecida pelo RH da Prefeitura.", A.ANEXO, "", True),
    ("APOSENTADORIA", None, S.BENEFICIOS, "Histórico de licenças e afastamentos (RH da PMBM)", "", A.ANEXO, "", True),
    ("APOSENTADORIA", None, S.BENEFICIOS, "Fichas financeiras / remunerações de contribuição", "", A.ANEXO, "", True),
    ("APOSENTADORIA", None, S.BENEFICIOS, "Certidão de Tempo de Contribuição (CTC) de outros regimes",
     "Se não houver tempo em outro regime, marque “não se aplica” e justifique.", A.ANEXO, "", True),
    ("APOSENTADORIA", Modality.PROFESSOR, S.BENEFICIOS,
     "Declaração de efetivo exercício em funções de magistério", "", A.ANEXO, "", True),
    ("APOSENTADORIA", None, S.BENEFICIOS, "Relatório de instrução (tempo, enquadramento e cálculo)",
     "Gerado pelo sistema no envio ao Jurídico.", A.SISTEMA, DocumentKind.RELATORIO_INSTRUCAO, True),
    # ---------------- pensão por morte (MM-PENSAO)
    ("PENSAO", None, S.BENEFICIOS, "Requerimento de pensão assinado pelo dependente (ou representante legal)", "",
     A.ANEXO, "", True),
    ("PENSAO", None, S.BENEFICIOS, "Certidão de óbito do instituidor", "", A.ANEXO, "", True),
    ("PENSAO", None, S.BENEFICIOS, "Documento de identidade e CPF dos dependentes", "", A.ANEXO, "", True),
    ("PENSAO", None, S.BENEFICIOS, "Certidão de casamento / nascimento ou prova de união estável e dependência", "",
     A.ANEXO, "", True),
    ("PENSAO", None, S.BENEFICIOS, "Comprovante de residência dos dependentes", "", A.ANEXO, "", True),
    ("PENSAO", None, S.BENEFICIOS, "Assentamentos funcionais e fichas financeiras do instituidor (RH da PMBM)",
     "Exigido quando o instituidor estava em atividade; se era aposentado, marque “não se aplica”.", A.ANEXO, "", True),
    ("PENSAO", None, S.BENEFICIOS, "Relatório de instrução (cotas e cálculo)", "Gerado pelo sistema no envio ao Jurídico.",
     A.SISTEMA, DocumentKind.RELATORIO_INSTRUCAO, True),
    # ---------------- revisão (MM-REVEBENEF)
    ("REVISAO", None, S.BENEFICIOS, "Requerimento de revisão assinado pelo requerente", "", A.ANEXO, "", True),
    ("REVISAO", None, S.BENEFICIOS, "Documentos que fundamentam o pedido de revisão", "", A.ANEXO, "", True),
    ("REVISAO", None, S.BENEFICIOS, "Relatório de instrução da revisão", "Gerado pelo sistema no envio ao Jurídico.",
     A.SISTEMA, DocumentKind.RELATORIO_INSTRUCAO, True),
    ("REVISAO", None, S.JURIDICO, "Processo original de concessão (enviado pelo Arquivo)",
     "O Jurídico solicita ao Arquivo o processo original antes do parecer (MM-REVEBENEF).", A.ANEXO, "", True),
]
# Itens comuns a todos os tipos (atos dos demais setores)
COMMON = [
    (S.JURIDICO, "Parecer jurídico", "Gerado pelo sistema ao registrar o parecer favorável.", A.SISTEMA,
     DocumentKind.PARECER_JURIDICO, True, ("APOSENTADORIA", "PENSAO", "REVISAO")),
    (S.CONTROLE, "Análise de conformidade", "Gerada pelo sistema ao registrar a conformidade.", A.SISTEMA,
     DocumentKind.PARECER_CONTROLE, True, ("APOSENTADORIA", "PENSAO")),
    (S.PRESIDENCIA, "Portaria assinada", "Gerada pelo sistema na assinatura da Presidência.", A.SISTEMA,
     DocumentKind.PORTARIA, True, ("APOSENTADORIA", "PENSAO", "REVISAO")),
    (S.FOLHA, "Cópia da publicação da portaria (Notícia Oficial)", "Anexe a página da publicação.", A.ANEXO, "", True,
     ("APOSENTADORIA", "PENSAO", "REVISAO")),
]

# Documentos do checklist que também são guardados no cadastro da pessoa do processo (nova versão)
PERSON_DOC_BY_NAME = {
    "Documento de identidade e CPF do servidor": "IDENTIDADE",
    "Comprovante de residência": "RESIDENCIA",
    "Certidão de Tempo de Contribuição (CTC) de outros regimes": "CTC",
    "Laudo da junta médica oficial": "LAUDO",
    "Certidão de óbito do instituidor": "CERT_OBITO",
}
# Documentos que permitem conferir e atualizar dados do cadastro na hora de anexar
EDITABLE_DATA = {"RESIDENCIA": "endereco", "IDENTIDADE": "identidade"}

SECTOR_ORDER = {s: i for i, s in enumerate(ChecklistSector.values)}
CLOSED_STAGES = {"IMPLANTADO", "INDEFERIDO", "ANULADO", "DESISTENCIA"}


def ensure_default_templates(institution) -> int:
    """Carrega a sugestão inicial se a instituição ainda não tem nenhum item de checklist cadastrado."""
    if ChecklistTemplate.objects.filter(institution=institution).exists():
        return 0
    rows = [ChecklistTemplate(institution=institution, concession_kind=k, modality=m, sector=s, name=n, help_text=h,
                              source=src, system_kind=sk, required=req, order=i,
                              person_doc_type=PERSON_DOC_BY_NAME.get(n, ""))
            for i, (k, m, s, n, h, src, sk, req) in enumerate(DEFAULT_CHECKLIST)]
    for j, (s, n, h, src, sk, req, kinds) in enumerate(COMMON):
        rows += [ChecklistTemplate(institution=institution, concession_kind=k, sector=s, name=n, help_text=h,
                                   source=src, system_kind=sk, required=req, order=100 + j) for k in kinds]
    ChecklistTemplate.objects.bulk_create(rows)
    return len(rows)


def _applies(t: ChecklistTemplate, c) -> bool:
    if t.concession_kind != c.kind:
        return False
    if t.modality is None:
        return True
    teacher = bool(c.rule_id and c.rule.for_teacher)
    return c.modality == t.modality or (t.modality == Modality.PROFESSOR and teacher)


@transaction.atomic
def sync(c) -> list[ChecklistItem]:
    """Monta/atualiza o checklist do processo conforme os modelos ativos e a modalidade enquadrada."""
    if c.stage in CLOSED_STAGES:  # processo encerrado: o checklist fica como estava
        return sorted(c.checklist.select_related("attachment", "document", "done_by"),
                      key=lambda i: (SECTOR_ORDER.get(i.sector, 9), i.order, i.name))
    ensure_default_templates(c.institution)
    templates = [t for t in ChecklistTemplate.objects.filter(institution=c.institution, active=True) if _applies(t, c)]
    existing = {i.template_id: i for i in c.checklist.all()}
    wanted = {t.pk for t in templates}
    for t in templates:
        if t.pk not in existing:
            ChecklistItem.objects.create(institution=c.institution, concession=c, template=t, sector=t.sector,
                                         name=t.name, help_text=t.help_text, source=t.source,
                                         system_kind=t.system_kind, required=t.required, order=t.order,
                                         person_doc_type=t.person_doc_type)
    # Item que deixou de se aplicar (ex.: mudou a modalidade) sai só se nada foi registrado nele
    for tid, item in existing.items():
        if tid not in wanted and item.status == ChecklistStatus.PENDENTE and not item.attachment_id:
            item.delete()
    return sorted(c.checklist.select_related("attachment", "document", "done_by"),
                  key=lambda i: (SECTOR_ORDER.get(i.sector, 9), i.order, i.name))


def current_sector(c) -> str | None:
    return SECTOR_BY_STAGE.get(c.stage)


def _require_editable(c, item: ChecklistItem):
    if item.concession_id != c.pk:
        raise BusinessRuleError("Item de outro processo.")
    if current_sector(c) != item.sector:
        raise BusinessRuleError(f"Este documento é do setor {ChecklistSector(item.sector).label}; só pode ser alterado "
                                "enquanto o processo estiver com esse setor.")
    if item.source == ChecklistSource.SISTEMA:
        raise BusinessRuleError("Este documento é gerado pelo sistema no ato do setor.")


@transaction.atomic
def attach(c, item: ChecklistItem, upload, user, data: dict | None = None) -> ChecklistItem:
    """
    Anexa o arquivo ao processo do Protocolo (com SHA-256) e cumpre o item. O anexo anterior permanece no processo.
    Se o item é um documento pessoal, guarda também no cadastro (nova versão) e, se vierem dados conferidos
    (endereço do comprovante, RG da identidade), atualiza o cadastro sem apagar o histórico.
    """
    from django.core.files.base import ContentFile

    from apps.people.services import ALLOWED_CONTENT_TYPES, MAX_DOCUMENT_BYTES
    from apps.protocolo.models import Attachment

    _require_editable(c, item)
    if upload is None:
        raise BusinessRuleError("Selecione o arquivo.")
    if upload.size > MAX_DOCUMENT_BYTES or getattr(upload, "content_type", "") not in ALLOWED_CONTENT_TYPES:
        raise BusinessRuleError("Envie PDF, JPG ou PNG de até 10 MB.")
    content = upload.read()
    sha = hashlib.sha256(content).hexdigest()
    att = Attachment(institution=c.institution, process=c.process,
                     description=f"Checklist ({ChecklistSector(item.sector).label}): {item.name}"[:255],
                     file_name=upload.name[:255], file_size=len(content), content_type=upload.content_type, sha256=sha)
    ext = "." + upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    att.file.save(f"{sha[:16]}{ext}", ContentFile(content), save=False)
    att.save()
    item.attachment, item.sha256, item.status, item.note = att, sha, ChecklistStatus.CUMPRIDO, ""
    item.done_by, item.done_at = user, timezone.now()
    if item.person_doc_type and c.person_id:
        item.person_document = _to_cadastro(c, item, content, upload)
        if data:
            update_cadastro(c.person, item.person_doc_type, data, user, c)
    item.save()
    return item


def _to_cadastro(c, item, content, upload):
    """Cópia do arquivo nos documentos da pessoa (cadastro). Se já for a versão atual, reaproveita."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.people.models import Document
    from apps.people.services import upload_document

    sha = hashlib.sha256(content).hexdigest()
    same = Document.objects.filter(person=c.person, doc_type=item.person_doc_type, sha256=sha).first()
    if same:
        return same
    f = SimpleUploadedFile(upload.name, content, content_type=upload.content_type)
    return upload_document(c.person, item.person_doc_type, f, description=f"Anexado no processo {c.process.code}")


def update_cadastro(person, doc_type: str, data: dict, user, c=None):
    """Atualiza o cadastro com os dados conferidos no documento (endereço = nova vigência; RG = auditado)."""
    from apps.audit.services import log_event
    from apps.core.validators import only_digits
    from apps.people.models import Address
    from apps.people.services import add_address

    kind = EDITABLE_DATA.get(doc_type)
    origin = f" (processo {c.process.code})" if c else ""
    if kind == "endereco":
        fields = {k: (data.get(k) or "").strip() for k in ("cep", "street", "number", "complement", "district", "city", "uf")}
        fields["cep"] = only_digits(fields["cep"])[:8]
        if not fields["street"] or not fields["city"]:
            raise BusinessRuleError("Endereço: informe pelo menos logradouro e cidade.")
        today = timezone.localdate()
        cur = Address.objects.filter(person=person, valid_to__isnull=True).first()
        same = cur and all((getattr(cur, k) or "") == v for k, v in fields.items())
        if same:
            return
        if cur and cur.valid_from >= today:
            raise BusinessRuleError("O endereço já foi alterado hoje; corrija pelo cadastro.")
        add_address(person, valid_from=today, **fields)
        log_event("UPDATE", module="cadastros.segurados", obj=person,
                  object_repr=f"Endereço atualizado pelo comprovante de residência{origin}")
    elif kind == "identidade":
        changes = {}
        for k in ("rg_number", "rg_issuer", "rg_uf"):
            v = (data.get(k) or "").strip()
            if v and v != (getattr(person, k) or ""):
                changes[k] = v
        if data.get("rg_date"):
            from datetime import date

            try:
                d = date.fromisoformat(data["rg_date"])
            except ValueError:
                raise BusinessRuleError("Data de expedição do RG inválida.")
            if d != person.rg_date:
                changes["rg_date"] = d
        if changes:
            old = {k: str(getattr(person, k) or "") for k in changes}
            for k, v in changes.items():
                setattr(person, k, v)
            person.save()
            log_event("UPDATE", module="cadastros.segurados", obj=person,
                      object_repr=f"Identidade atualizada pelo documento anexado{origin}",
                      extra={"antes": old, "depois": {k: str(v) for k, v in changes.items()}})


@transaction.atomic
def waive(c, item: ChecklistItem, note: str, user) -> ChecklistItem:
    _require_editable(c, item)
    if not note or len(note.strip()) < 15:
        raise BusinessRuleError("Justifique por que o documento não se aplica (mínimo de 15 caracteres).")
    item.status, item.note, item.attachment, item.sha256 = ChecklistStatus.NAO_SE_APLICA, note.strip(), None, ""
    item.done_by, item.done_at = user, timezone.now()
    item.save()
    return item


@transaction.atomic
def reopen(c, item: ChecklistItem, user) -> ChecklistItem:
    """Volta o item a pendente (o arquivo anterior continua no Protocolo, como histórico)."""
    _require_editable(c, item)
    item.status, item.note, item.attachment, item.sha256 = ChecklistStatus.PENDENTE, "", None, ""
    item.done_by, item.done_at = user, timezone.now()
    item.save()
    return item


def pending(c, sector: str) -> list[ChecklistItem]:
    return [i for i in sync(c) if i.sector == sector and i.required and i.source == ChecklistSource.ANEXO
            and i.status == ChecklistStatus.PENDENTE]


def require_complete(c, sector: str):
    """Trava: o setor não libera o processo com documento obrigatório pendente."""
    missing = pending(c, sector)
    if missing:
        raise BusinessRuleError(
            f"Checklist de {ChecklistSector(sector).label} incompleto — anexe ou justifique antes de liberar o processo: "
            + "; ".join(i.name for i in missing))


def fulfil_system(c, sector: str, doc, user):
    """Liga o documento gerado pelo sistema ao item correspondente do checklist."""
    for item in c.checklist.filter(sector=sector, source=ChecklistSource.SISTEMA, system_kind=doc.kind):
        item.document, item.sha256, item.status = doc, doc.sha256, ChecklistStatus.CUMPRIDO
        item.done_by, item.done_at = user, timezone.now()
        item.save()


def seal(c, sector: str, user) -> dict:
    """
    Assinatura do checklist do setor: código SHA-256 sobre os itens (nome, situação, hash de cada arquivo,
    justificativa), o processo e o assinante. Vai para a trilha (no ato do setor) e para o andamento do Protocolo.
    """
    from apps.protocolo.models import Movement, MovementKind

    items = [i for i in sync(c) if i.sector == sector]
    manifest = [{"documento": i.name, "situacao": i.status, "sha256": i.sha256, "justificativa": i.note}
                for i in items]
    at = timezone.now()
    payload = {"processo": c.process.code, "concessao": str(c.pk), "setor": sector, "itens": manifest,
               "assinante": str(user.pk), "em": at.isoformat()}
    code = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    done = sum(1 for i in items if i.status != ChecklistStatus.PENDENTE)
    def line(m):
        if m["sha256"]:
            return f"SHA-256 {m['sha256'][:16]}…"
        if m["situacao"] == ChecklistStatus.NAO_SE_APLICA:
            return "não se aplica — " + m["justificativa"]
        return "pendente (opcional)"

    lines = "\n".join(f"  • {m['documento']}: {line(m)}" for m in manifest)
    Movement.objects.create(
        institution=c.institution, process=c.process, kind=MovementKind.DESPACHO, from_sector=c.process.current_sector,
        occurred_at=at, due_date_after=c.process.due_date,
        text=(f"Checklist de {ChecklistSector(sector).label} ASSINADO ELETRONICAMENTE por "
              f"{user.full_name or user.username} em {timezone.localtime(at):%d/%m/%Y %H:%M} — {done} de {len(items)} "
              f"documento(s).\nCódigo de verificação (SHA-256): {code}\n{lines}")[:4000])
    return {"setor": sector, "hash_checklist": code, "itens": manifest, "assinado_em": at.isoformat()}
