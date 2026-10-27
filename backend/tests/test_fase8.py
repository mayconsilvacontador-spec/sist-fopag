from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.concessao.models import Benefit
from apps.folha.defaults import seed_payroll
from apps.folha.models import PayrollEntry
from apps.institutions.models import PayrollGroup
from apps.institutions.services import ensure_payroll_groups, set_parameter
from apps.people.models import Person

NEW_PASSWORD = "Nova-Senha-Portal-2026!"


@pytest.fixture
def base(institution):
    set_parameter(institution, "rgps.teto", "8157.41", date(2025, 1, 1))
    ensure_payroll_groups(institution)
    seed_payroll(institution)
    return PayrollGroup.objects.get(institution=institution, segment="PREVIDENCIARIO")


def _login(cpf, password):
    c = APIClient()
    r = c.post("/api/v1/portal/auth/token/", {"cpf": cpf, "password": password}, format="json")
    if r.status_code == 200:
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    return c, r


def test_portal_acesso_isolamento_e_consultas(institution, master, consulta, client_for, base):
    staff = client_for(master)
    ana = Person.objects.create(institution=institution, cpf="52998224725", name="Ana Segurada", birth_date=date(1958, 1, 1), sex=1)
    outro = Person.objects.create(institution=institution, cpf="11144477735", name="Outro", birth_date=date(1960, 1, 1), sex=2)
    for p in (ana, outro):
        Benefit.objects.create(institution=institution, kind="APOSENTADORIA", beneficiary=p, payroll_group=base,
                               start_date=date(2024, 1, 1), amount=Decimal("4000.00"))

    # Folha de 10/2025 fechada; folha de 11/2025 só calculada (não aparece no portal)
    rid = staff.post("/api/v1/folha/folhas/", {"year": 2025, "month": 10, "payroll_group": str(base.pk)}, format="json").json()["id"]
    for step in ("calculate", "check", "close"):
        staff.post(f"/api/v1/folha/folhas/{rid}/{step}/")
    rid2 = staff.post("/api/v1/folha/folhas/", {"year": 2025, "month": 11, "payroll_group": str(base.pk)}, format="json").json()["id"]
    staff.post(f"/api/v1/folha/folhas/{rid2}/calculate/")

    # Equipe cria o acesso (perfil de consulta não pode)
    assert client_for(consulta).post("/api/v1/portal-admin/acessos/", {"person": str(ana.pk)}, format="json").status_code == 403
    r = staff.post("/api/v1/portal-admin/acessos/", {"person": str(ana.pk)}, format="json")
    assert r.status_code == 201, r.json()
    temp = r.json()["senha_provisoria"]
    staff.post("/api/v1/portal-admin/acessos/", {"person": str(outro.pk)}, format="json")

    # Usuário do portal não entra pelo login interno
    assert APIClient().post("/api/v1/auth/token/", {"username": f"portal-{institution.short_name.lower()}-52998224725",
                                                    "password": temp}, format="json").status_code == 401
    assert _login("529.982.247-25", "errada")[1].status_code == 401

    c, r = _login("529.982.247-25", temp)
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    assert c.get("/api/v1/portal/contracheques/").status_code == 403  # troca obrigatória
    assert c.get("/api/v1/portal/me/").json()["must_change_password"] is True
    assert c.post("/api/v1/auth/change-password/", {"current_password": temp, "new_password": NEW_PASSWORD},
                  format="json").status_code == 200

    c, r = _login("52998224725", NEW_PASSWORD)
    assert r.status_code == 200
    me = c.get("/api/v1/portal/me/").json()
    assert me["pessoa"]["nome"] == "Ana Segurada"
    slips = c.get("/api/v1/portal/contracheques/").json()
    assert len(slips) == 1 and slips[0]["competencia"] == "10/2025"
    detail = c.get(f"/api/v1/portal/contracheques/{slips[0]['id']}/").json()
    assert detail["items"] and "memory" not in detail
    # Contracheque de outra pessoa: não encontrado
    other = PayrollEntry.objects.get(run_id=rid, beneficiary=outro)
    assert c.get(f"/api/v1/portal/contracheques/{other.pk}/").status_code == 404
    # Telas internas: bloqueadas
    for url in ("/api/v1/people/", "/api/v1/folha/folhas/", "/api/v1/beneficios/", "/api/v1/dashboard/"):
        assert c.get(url).status_code == 403, url
    assert c.get("/api/v1/auth/me/").json()["portal"] is True

    assert c.get("/api/v1/portal/informe-rendimentos/").json()["anos"] == [2025]
    inf = c.get("/api/v1/portal/informe-rendimentos/", {"year": 2025}).json()
    assert inf["quadro_3"]["1_rendimentos_tributaveis"] == "2096.02"  # 4.000 − parcela isenta 65+ (1.903,98)
    assert inf["quadro_4"]["1_parcela_isenta_65_anos"] == "1903.98"
    assert len(c.get("/api/v1/portal/beneficios/").json()) == 1

    # Solicitação e resposta da equipe
    req = c.post("/api/v1/portal/solicitacoes/", {"kind": "ATUALIZACAO", "subject": "Mudei de endereço",
                                                  "message": "Novo endereço: Rua B, 20"}, format="json")
    assert req.status_code == 201
    ans = staff.post(f"/api/v1/portal-admin/solicitacoes/{req.json()['id']}/answer/",
                     {"answer": "Endereço atualizado.", "status": "RESPONDIDA"}, format="json")
    assert ans.status_code == 200
    assert c.get("/api/v1/portal/solicitacoes/").json()[0]["answer"] == "Endereço atualizado."

    # Bloqueio do acesso
    acc_id = r.json()["institution_id"] and staff.get("/api/v1/portal-admin/acessos/", {"search": "Ana"}).json()["results"][0]["id"]
    staff.post(f"/api/v1/portal-admin/acessos/{acc_id}/deactivate/", {"justification": "Óbito comunicado pela família"},
               format="json")
    assert _login("52998224725", NEW_PASSWORD)[1].status_code == 401
