"""Regras do Cadastro Único (endereços e contas com vigência, documentos versionados)."""
import hashlib
from datetime import timedelta

from django.db import transaction

from apps.core.exceptions import BusinessRuleError

from .models import Address, BankAccount, Dependency, DependencyType, Document

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def _close_current(model, person, new_start):
    """Encerra a vigência do registro vigente no dia anterior ao novo."""
    current = model.objects.select_for_update().filter(person=person, valid_to__isnull=True).first()
    if current is None:
        return
    if current.valid_from >= new_start:
        raise BusinessRuleError(
            "A vigência do novo registro deve começar depois da vigência do registro atual "
            f"({current.valid_from:%d/%m/%Y})."
        )
    current.valid_to = new_start - timedelta(days=1)
    current.save(update_fields=["valid_to", "updated_at", "updated_by"])


@transaction.atomic
def add_address(person, **data) -> Address:
    _close_current(Address, person, data["valid_from"])
    return Address.objects.create(institution_id=person.institution_id, person=person, **data)


@transaction.atomic
def add_bank_account(person, **data) -> BankAccount:
    bank = data["bank"]
    if bank.institution_id != person.institution_id:
        raise BusinessRuleError("Banco de outra instituição.")
    _close_current(BankAccount, person, data["valid_from"])
    return BankAccount.objects.create(institution_id=person.institution_id, person=person, **data)


def validate_dependency(holder, dependent, kind, start_date):
    if holder.pk == dependent.pk:
        raise BusinessRuleError("A pessoa não pode ser dependente de si mesma.")
    if holder.institution_id != dependent.institution_id:
        raise BusinessRuleError("Titular e dependente devem ser da mesma instituição.")
    if start_date < dependent.birth_date:
        raise BusinessRuleError("O início da dependência não pode ser anterior ao nascimento do dependente.")
    if kind in (DependencyType.FILHO_INVALIDO, DependencyType.ENTEADO_INVALIDO, DependencyType.IRMAO_INVALIDO) \
            and not dependent.is_invalid:
        raise BusinessRuleError("Para dependência por invalidez, marque o dependente como inválido no Cadastro Único.")
    if Dependency.objects.filter(holder=holder, dependent=dependent, end_date__isnull=True).exists():
        raise BusinessRuleError("Já existe dependência ativa entre essas pessoas. Encerre-a antes de criar outra.")


@transaction.atomic
def upload_document(person, doc_type: str, uploaded_file, description: str = "") -> Document:
    name = uploaded_file.name or "documento"
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    content_type = getattr(uploaded_file, "content_type", "") or ""
    if ext not in ALLOWED_EXTENSIONS or content_type not in ALLOWED_CONTENT_TYPES:
        raise BusinessRuleError("Envie arquivos PDF, JPG ou PNG.")
    if uploaded_file.size > MAX_DOCUMENT_BYTES:
        raise BusinessRuleError("O arquivo excede o limite de 10 MB.")
    content = uploaded_file.read()
    if ext == ".pdf" and not content.startswith(b"%PDF"):
        raise BusinessRuleError("O conteúdo do arquivo não é um PDF válido.")
    sha = hashlib.sha256(content).hexdigest()
    previous = Document.objects.select_for_update().filter(person=person, doc_type=doc_type).order_by("-version")
    last = previous.first()
    if last and last.sha256 == sha:
        raise BusinessRuleError("Este arquivo é idêntico à versão atual do documento.")
    previous.filter(superseded=False).update(superseded=True)
    doc = Document(
        institution_id=person.institution_id, person=person, doc_type=doc_type, description=description,
        file_name=name[:255], file_size=len(content), content_type=content_type, sha256=sha,
        version=(last.version + 1) if last else 1,
    )
    uploaded_file.seek(0)
    doc.file.save(f"{sha[:16]}{ext}", uploaded_file, save=False)
    doc.save()
    return doc
