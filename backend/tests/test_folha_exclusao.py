"""Exclusão de folha aberta por engano: senha, justificativa, só a última da massa, nunca folha paga com beneficiário."""
from datetime import date
from decimal import Decimal

from apps.audit.models import AuditLog
from apps.concessao.models import Benefit
from apps.folha.models import PayrollRun

from .conftest import PASSWORD
from .test_fase5 import folha, person  # noqa: F401 (fixture)

JUST = "Folha aberta por engano na massa errada"


def _abrir(c, group, month):
    r = c.post("/api/v1/folha/folhas/", {"year": 2025, "month": month, "payroll_group": str(group.pk)}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()["id"]


def _excluir(c, rid, **kw):
    body = {"justification": JUST, "password": PASSWORD, **kw}
    return c.post(f"/api/v1/folha/folhas/{rid}/excluir/", body, format="json")


def test_exclusao_de_folha(institution, master, consulta, client_for, folha):  # noqa: F811
    c = client_for(master)
    p = person(institution, 200000001, "Aposentada", date(1955, 1, 10))
    Benefit.objects.create(institution=institution, kind="APOSENTADORIA", beneficiary=p, payroll_group=folha,
                           start_date=date(2020, 1, 1), amount=Decimal("3000.00"))
    out = _abrir(c, folha, 10)
    assert c.post(f"/api/v1/folha/folhas/{out}/calculate/").status_code == 200

    # Sem permissão, sem senha certa ou sem justificativa: recusa
    assert _excluir(client_for(consulta), out).status_code == 403
    assert _excluir(c, out, password="errada-123").status_code == 409
    assert _excluir(c, out, justification="curta").status_code == 409

    # Fecha outubro e abre novembro: outubro deixa de ser a última e não pode ser excluída
    run = PayrollRun.objects.get(pk=out)
    assert c.post(f"/api/v1/folha/folhas/{out}/check/").status_code == 200
    assert c.post(f"/api/v1/folha/folhas/{out}/close/").status_code == 200
    nov = _abrir(c, folha, 11)
    r = _excluir(c, out)
    assert r.status_code == 409 and "posterior" in r.json()["detail"]

    # A última (novembro) sai, com registro na auditoria; depois outubro (fechada) também pode sair
    assert _excluir(c, nov).status_code == 204
    assert not PayrollRun.objects.filter(pk=nov).exists()
    assert AuditLog.objects.filter(action="DELETE", module="folha.folha_mensal", object_id=nov,
                                   justification=JUST).exists()

    # Paga com beneficiário: nunca
    run.refresh_from_db()
    assert c.post(f"/api/v1/folha/folhas/{out}/pay/", {"payment_date": "2025-10-30"}, format="json").status_code == 200
    r = _excluir(c, out)
    assert r.status_code == 409 and "paga" in r.json()["detail"]
