"""
Legislação própria de cada RPPS/ente: cadastro de normas (`LegalNorm`) e aplicação de PACOTES-MODELO de regras de
aposentadoria (`rules.PACKAGES`). Nada de regra fixa de um ente no código: o pacote cria/atualiza as regras da
instituição (código igual = atualiza, com o valor anterior na auditoria; regras fora do pacote ficam inativas — nunca
são apagadas, porque concessões antigas apontam para elas).
"""
import hashlib
from datetime import date

from django.core.files.base import ContentFile
from django.db import transaction

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from .models import NORM_SUBJECTS, LegalNorm, NormKind, RetirementRule
from .rules import PACKAGES, package_rules

MAX_PDF = 20 * 1024 * 1024
RULE_FIELDS = ("name", "legal_basis", "engine", "group", "for_teacher", "params", "valid_from", "valid_to", "proventos",
               "paridade", "gives_permanence_bonus", "notes")


def main_norm(institution, subject: str = "APOSENTADORIA"):
    """Norma local vigente mais recente sobre o assunto (usada quando a regra não aponta para uma norma)."""
    for n in LegalNorm.objects.filter(institution=institution, active=True).order_by("-valid_from", "-date"):
        if subject in (n.subjects or []):
            return n
    return None


def _clean(data: dict) -> dict:
    kind = data.get("kind")
    if kind not in NormKind.values:
        raise BusinessRuleError("Escolha o tipo da norma.")
    number = str(data.get("number") or "").strip()[:30]
    if not number:
        raise BusinessRuleError("Informe o número da norma.")
    subjects = [s for s in (data.get("subjects") or []) if s in NORM_SUBJECTS]

    def d(key):
        v = data.get(key)
        if not v:
            return None
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            raise BusinessRuleError(f"Data inválida ({key}).")

    out = {"kind": kind, "number": number, "date": d("date"), "publication_date": d("publication_date"),
           "valid_from": d("valid_from"), "valid_to": d("valid_to"), "summary": str(data.get("summary") or "")[:500],
           "subjects": subjects, "url": str(data.get("url") or "")[:200]}
    if out["valid_from"] and out["valid_to"] and out["valid_to"] < out["valid_from"]:
        raise BusinessRuleError("A vigência final não pode ser anterior à inicial.")
    return out


def _attach(norm: LegalNorm, upload):
    content = upload.read()
    if len(content) > MAX_PDF:
        raise BusinessRuleError("PDF acima de 20 MB.")
    if not content.startswith(b"%PDF"):
        raise BusinessRuleError("O arquivo da norma deve ser um PDF.")
    norm.sha256 = hashlib.sha256(content).hexdigest()
    norm.file_name = (upload.name or "norma.pdf")[:255]
    norm.file.save(f"{norm.sha256[:16]}.pdf", ContentFile(content), save=False)


@transaction.atomic
def save_norm(institution, data: dict, upload=None, norm: LegalNorm | None = None) -> LegalNorm:
    values = _clean(data)
    created = norm is None
    old = None if created else {k: str(getattr(norm, k)) for k in values}
    norm = norm or LegalNorm(institution=institution)
    for k, v in values.items():
        setattr(norm, k, v)
    if upload is not None:
        _attach(norm, upload)
    norm.save()
    log_event("CREATE" if created else "UPDATE", module="previdenciaria.regras", obj=norm,
              object_repr=f"Legislação do RPPS — {norm.citation}", old=old,
              new={k: str(getattr(norm, k)) for k in values})
    return norm


def packages_info(institution) -> dict:
    rules = RetirementRule.objects.filter(institution=institution)
    current = rules.filter(active=True).exclude(package="").values_list("package", flat=True).first() or ""
    return {"pacotes": [{"codigo": k, **v} for k, v in PACKAGES.items()], "pacote_atual": current,
            "regras_ativas": rules.filter(active=True).count(), "regras_total": rules.count()}


@transaction.atomic
def apply_package(institution, package: str, *, reform: date | None, norm: LegalNorm | None, justification: str, user) -> dict:
    from apps.institutions.services import get_parameter, set_parameter

    if package not in PACKAGES:
        raise BusinessRuleError("Pacote de regras inválido.")
    if len((justification or "").strip()) < 10:
        raise BusinessRuleError("Informe a justificativa (mínimo de 10 caracteres): ex.: \"Implantação — Lei X\".")
    if PACKAGES[package]["needs_reform"] and reform is None:
        raise BusinessRuleError("Informe a data em que a reforma local começou a valer.")
    if norm is not None and norm.institution_id != institution.pk:
        raise BusinessRuleError("Norma de outra instituição.")
    local = norm.citation if norm else ""
    try:
        data = package_rules(package, reform, local)
    except ValueError as e:
        raise BusinessRuleError(str(e))
    codes, created, updated = set(), 0, 0
    for r in data:
        values = {"for_teacher": False, "gives_permanence_bonus": True, "valid_from": None, "valid_to": None, "notes": "",
                  **{k: r[k] for k in r if k in RULE_FIELDS}}
        codes.add(r["code"])
        rule = RetirementRule.objects.filter(institution=institution, code=r["code"]).first()
        if rule is None:
            RetirementRule.objects.create(institution=institution, code=r["code"], norm=norm, package=package,
                                          active=True, **values)
            created += 1
            continue
        old = {k: str(getattr(rule, k)) for k in values}
        for k, v in values.items():
            setattr(rule, k, v)
        rule.norm, rule.package, rule.active = norm, package, True
        rule.save()
        updated += 1
        log_event("UPDATE", module="previdenciaria.regras", obj=rule, old=old,
                  new={k: str(getattr(rule, k)) for k in values}, justification=justification)
    off = RetirementRule.objects.filter(institution=institution, active=True).exclude(code__in=codes)
    inactivated = off.count()
    off.update(active=False)
    aviso = ""
    if reform is not None:
        cur = get_parameter(institution, "previdencia.vigencia_reforma_local")
        if str(cur or "")[:10] != reform.isoformat():
            try:
                set_parameter(institution, "previdencia.vigencia_reforma_local", reform.isoformat(), reform,
                              description="Início da vigência da reforma previdenciária local", change_reason=justification)
            except BusinessRuleError as e:
                aviso = f"Data da reforma não gravada em Parâmetros: {e}"
    log_event("UPDATE", module="previdenciaria.regras", object_repr=f"Pacote de regras aplicado: {PACKAGES[package]['label']}",
              justification=justification, extra={"pacote": package, "criadas": created, "atualizadas": updated,
                                                  "inativadas": inactivated, "norma": local,
                                                  "reforma": reform.isoformat() if reform else None})
    return {"pacote": package, "criadas": created, "atualizadas": updated, "inativadas": inactivated, "aviso": aviso}
