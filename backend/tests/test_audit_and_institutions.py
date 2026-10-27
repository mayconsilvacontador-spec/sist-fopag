from datetime import date

import pytest
from django.db import connection, transaction
from django.db.utils import DatabaseError

from apps.audit.models import AuditLog, ImmutableAuditError
from apps.core.validators import is_valid_cnpj, is_valid_cpf
from apps.institutions.models import Competence, Parameter


def test_update_generates_diff(master, institution, client_for):
    resp = client_for(master).patch("/api/v1/institution/current/", {"city": "Volta Redonda"}, format="json")
    assert resp.status_code == 200
    log = AuditLog.objects.filter(action="UPDATE", object_type="institutions.institution").latest("id")
    assert log.old_values == {"city": "Barra Mansa"}
    assert log.new_values == {"city": "Volta Redonda"}
    assert log.username == "master"
    assert log.verify()


def test_audit_log_is_immutable_in_app_and_database(master, institution, client_for):
    client_for(master).patch("/api/v1/institution/current/", {"city": "X"}, format="json")
    log = AuditLog.objects.latest("id")
    with pytest.raises(ImmutableAuditError):
        log.justification = "adulterado"
        log.save()
    with pytest.raises(ImmutableAuditError):
        log.delete()
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("UPDATE audit_logs SET justification='x' WHERE id=%s", [log.pk])
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            AuditLog.objects.filter(pk=log.pk).delete()


def test_parameter_versioning_never_overwrites(master, institution, client_for):
    c = client_for(master)
    r1 = c.post("/api/v1/parameters/", {"key": "teto_rgps", "value": "8157.41",
                                        "valid_from": "2026-01-01", "description": "Teto do RGPS"}, format="json")
    assert r1.status_code == 201, r1.data
    r2 = c.post("/api/v1/parameters/", {"key": "teto_rgps", "value": "8500.00", "valid_from": "2027-01-01"},
                format="json")
    assert r2.status_code == 409  # exige motivo
    r3 = c.post("/api/v1/parameters/", {"key": "teto_rgps", "value": "8500.00", "valid_from": "2027-01-01",
                                        "change_reason": "Portaria interministerial 2027"}, format="json")
    assert r3.status_code == 201
    v1, v2 = Parameter.objects.filter(key="teto_rgps").order_by("version")
    assert v1.valid_to == date(2026, 12, 31) and v1.value == "8157.41"
    assert v2.version == 2 and v2.valid_to is None


def test_reopen_competence_requires_justification(master, institution, client_for):
    comp = Competence.objects.get(institution=institution, month=9)
    c = client_for(master)
    assert c.post(f"/api/v1/competences/{comp.pk}/close/").status_code == 200
    assert c.post(f"/api/v1/competences/{comp.pk}/reopen/", {"justification": "curta"}, format="json").status_code == 409
    resp = c.post(f"/api/v1/competences/{comp.pk}/reopen/",
                  {"justification": "Correção de lançamento identificada na conferência"}, format="json")
    assert resp.status_code == 200
    log = AuditLog.objects.filter(action="REOPEN").latest("id")
    assert "conferência" in log.justification


def test_dashboard_uses_real_data(master, client_for):
    resp = client_for(master).get("/api/v1/dashboard/?plano=FINANCEIRO")
    assert resp.status_code == 200
    assert all(card["source"] == "real" for card in resp.data["cards"])
    assert resp.data["cabecalho"]["competencia_referencia"]["rotulo"] == "Setembro/2026"
    cards = {c["key"]: c["value"] for c in resp.data["cards"]}
    # Sem benefícios nem folha calculada: contagens zeradas e valores vazios (nada de números inventados)
    assert cards["total_beneficiarios"] == 0 and cards["folha_bruta"] is None
    assert resp.data["cabecalho"]["folha"]["status"] == "Não aberta"


def test_alert_checks_detect_missing_plan(master, institution, client_for):
    institution_plans = institution  # noqa: F841
    from apps.institutions.models import BenefitPlan
    BenefitPlan.objects.filter(code="PREV").update(active=False)
    resp = client_for(master).post("/api/v1/alerts/run-checks/")
    assert resp.status_code == 200
    alerts = client_for(master).get("/api/v1/alerts/").data["results"]
    assert any(a["code"] == "PLANO_SEGREGACAO_AUSENTE" and a["severity"] == "CRITICO" for a in alerts)


def test_document_validators():
    assert is_valid_cpf("529.982.247-25")
    assert not is_valid_cpf("529.982.247-24")
    assert is_valid_cnpj("11.222.333/0001-81")
    assert not is_valid_cnpj("11.222.333/0001-80")
