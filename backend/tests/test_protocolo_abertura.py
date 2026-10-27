"""Todos os setores abrem processos no Protocolo; fora do próprio setor, o processo chega aguardando recebimento."""
from apps.accounts.models import Role
from apps.accounts.services import sync_permissions
from apps.protocolo.models import ProcessType, Sector
from tests.conftest import make_user


def test_qualquer_setor_abre_processo(institution, client_for):
    folha = make_user(institution, "folhauser", "FOLHA")
    juridico = make_user(institution, "jur", "JURIDICO")
    ben = Sector.objects.create(institution=institution, name="Benefícios", code="BEN")
    jur = Sector.objects.create(institution=institution, name="Jurídico", code="JUR")
    jur.members.add(juridico)
    ptype = ProcessType.objects.create(institution=institution, name="Requerimento", deadline_days=30,
                                       sector_deadline_days=5)
    body = {"process_type": str(ptype.pk), "sector": str(ben.pk), "subject": "Requerimento geral",
            "interested_name": "Fulano"}

    # Usuário da Folha (sem setor) abre processo para Benefícios: chega aguardando recebimento
    c = client_for(folha)
    destinos = c.get("/api/v1/protocol/sectors/destinos/").json()
    assert {d["code"] for d in destinos} == {"BEN", "JUR"} and not any(d["meu"] for d in destinos)
    r = c.post("/api/v1/protocol/processes/", body, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["pending_receipt"] is True and r.json()["sector_due_date"] is None

    # Quem é do setor abre direto (sem recebimento)
    r = client_for(juridico).post("/api/v1/protocol/processes/", {**body, "sector": str(jur.pk)}, format="json")
    assert r.status_code == 201 and r.json()["pending_receipt"] is False and r.json()["sector_due_date"]


def test_perfis_existentes_recebem_permissao_do_protocolo(institution):
    role = Role.objects.get(code="FOLHA", institution__isnull=True)
    role.role_permissions.filter(permission__module_id="protocolo.processos").delete()  # perfil antigo, sem Protocolo
    sync_permissions(verbose=False)
    acts = set(role.permissions.filter(module__code="protocolo.processos").values_list("action", flat=True))
    assert acts == {"visualizar", "incluir", "editar"}
    consulta = Role.objects.get(code="CONSULTA", institution__isnull=True)
    assert "incluir" not in set(consulta.permissions.filter(module__code="protocolo.processos")
                                .values_list("action", flat=True))
