from apps.accounts.models import Role
from apps.audit.models import AuditLog

from .conftest import make_user


def test_consulta_can_view_but_not_edit_users(consulta, client_for):
    c = client_for(consulta)
    # CONSULTA não possui acesso à administração
    assert c.get("/api/v1/users/").status_code == 403
    assert c.get("/api/v1/dashboard/").status_code == 200
    assert c.post("/api/v1/users/", {"username": "x", "full_name": "Fulano de Tal"}, format="json").status_code == 403


def test_master_creates_user_with_temp_password_and_roles(master, client_for):
    folha = Role.objects.get(code="FOLHA", institution__isnull=True)
    resp = client_for(master).post(
        "/api/v1/users/",
        {"username": "Joao", "full_name": "João  da Silva", "cpf": "529.982.247-25", "role_ids": [str(folha.pk)]},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["username"] == "joao"
    assert resp.data["full_name"] == "João da Silva"
    assert resp.data["temporary_password"]
    assert [r["code"] for r in resp.data["roles"]] == ["FOLHA"]
    assert AuditLog.objects.filter(action="PERMISSION_CHANGE", object_id=resp.data["id"]).exists()


def test_invalid_cpf_rejected(master, client_for):
    resp = client_for(master).post(
        "/api/v1/users/", {"username": "maria", "full_name": "Maria Souza", "cpf": "111.111.111-11"}, format="json"
    )
    assert resp.status_code == 400
    assert "cpf" in resp.data


def test_only_master_grants_master(institution, client_for):
    admin = make_user(institution, "admin", "ADMINISTRADOR")
    target = make_user(institution, "alvo", "CONSULTA")
    master_role = Role.objects.get(code="MASTER", institution__isnull=True)
    resp = client_for(admin).patch(
        f"/api/v1/users/{target.pk}/", {"role_ids": [str(master_role.pk)]}, format="json"
    )
    assert resp.status_code == 409


def test_role_permissions_change_is_audited(master, client_for):
    c = client_for(master)
    role = c.post("/api/v1/roles/", {"code": "analista", "name": "Analista"}, format="json").data
    assert role["code"] == "ANALISTA"
    resp = c.put(f"/api/v1/roles/{role['id']}/permissions/",
                 {"permissions": ["painel:visualizar", "alertas:visualizar"]}, format="json")
    assert resp.status_code == 200
    assert resp.data["permissions"] == ["alertas:visualizar", "painel:visualizar"]
    log = AuditLog.objects.filter(action="PERMISSION_CHANGE", object_id=role["id"]).get()
    assert sorted(log.new_values["adicionadas"]) == ["alertas:visualizar", "painel:visualizar"]


def test_master_role_permissions_are_locked(master, client_for):
    master_role = Role.objects.get(code="MASTER", institution__isnull=True)
    resp = client_for(master).put(f"/api/v1/roles/{master_role.pk}/permissions/", {"permissions": []}, format="json")
    assert resp.status_code == 409
