from django.core.cache import cache
from rest_framework.test import APIClient

from apps.audit.models import AuditLog

from .conftest import PASSWORD


def _login(username, password):
    cache.clear()  # zera o throttle entre chamadas do teste
    return APIClient().post("/api/v1/auth/token/", {"username": username, "password": password}, format="json")


def test_login_success_returns_tokens_and_audits(master):
    resp = _login("master", PASSWORD)
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data
    assert AuditLog.objects.filter(action="LOGIN", object_id=str(master.pk)).exists()


def test_login_failure_is_generic_and_audited(master):
    resp = _login("master", "errada")
    assert resp.status_code == 401
    assert resp.data["detail"] == "Usuário ou senha inválidos."
    resp2 = _login("naoexiste", "x")
    assert resp2.data["detail"] == resp.data["detail"]
    assert AuditLog.objects.filter(action="LOGIN_FAILED").count() == 2


def test_lockout_after_max_attempts(master, settings):
    settings.LOGIN_MAX_FAILED_ATTEMPTS = 3
    for _ in range(3):
        _login("master", "errada")
    resp = _login("master", PASSWORD)
    assert resp.status_code == 401
    assert resp.data["code"] == "usuario_bloqueado"


def test_me_returns_permissions(master, client_for):
    resp = client_for(master).get("/api/v1/auth/me/")
    assert resp.status_code == 200
    assert "admin.usuarios:editar" in resp.data["permissions"]
    assert resp.data["primary_role"] == "MASTER"
    assert resp.data["institution"]["short_name"] == "TESTE"


def test_must_change_password_blocks_other_endpoints(master, client_for):
    master.must_change_password = True
    master.save()
    c = client_for(master)
    assert c.get("/api/v1/auth/me/").status_code == 200
    resp = c.get("/api/v1/dashboard/")
    assert resp.status_code == 403
