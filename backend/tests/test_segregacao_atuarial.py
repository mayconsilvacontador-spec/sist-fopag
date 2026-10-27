import io
import zipfile

import pytest

from apps.actuarial import layouts
from apps.actuarial.models import ActuarialBase
from apps.audit.models import AuditLog
from apps.institutions.models import LifePurchase, PayrollGroup, Segment
from apps.institutions.services import segments_for_filter

JUST = {"justification": "Lei municipal autorizou a compra de vidas."}


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def enable_cv(client):
    return client.post("/api/v1/institution/current/life-purchase/", {"enabled": True, **JUST}, format="json")


def test_ativar_compra_vidas_cria_terceira_folha(institution, master, client_for):
    c = client_for(master)
    assert c.post("/api/v1/institution/current/life-purchase/", {"enabled": True}, format="json").status_code == 409

    r = enable_cv(c)
    assert r.status_code == 200 and r.json()["life_purchase_enabled"] is True
    groups = {g["segment"]: g for g in c.get("/api/v1/payroll-groups/").json()}
    assert set(groups) == {"FINANCEIRO", "PREVIDENCIARIO", "COMPRA_VIDAS"}
    assert groups["COMPRA_VIDAS"]["plan_kind"] == "PREVIDENCIARIO"
    assert c.get("/api/v1/auth/me/").json()["institution"]["life_purchase_enabled"] is True
    log = AuditLog.objects.filter(module="admin.instituicao", object_id=str(institution.pk)).latest("id")
    assert log.justification.startswith("Lei municipal") and log.new_values == {"possui_compra_de_vidas": True}


def test_lotes_compra_vidas(institution, master, client_for):
    c = client_for(master)
    body = {"cutoff_date": "2025-12-31", "legal_act": "Lei nº 1.234/2025", "transferred_amount": "1500000.00"}
    assert c.post("/api/v1/life-purchases/", body, format="json").status_code == 400  # CV desativada

    enable_cv(c)
    r = c.post("/api/v1/life-purchases/", body, format="json")
    assert r.status_code == 201, r.json()
    lot = r.json()
    assert lot["number"] == 1 and lot["origin_plan_code"] == "FIN" and lot["destination_plan_code"] == "PREV"
    assert c.post("/api/v1/life-purchases/", {**body, "effective_date": "2025-01-01"}, format="json").status_code == 400

    # Com lote ativo não é possível desativar
    off = {"enabled": False, **JUST}
    assert c.post("/api/v1/institution/current/life-purchase/", off, format="json").status_code == 409
    c.patch(f"/api/v1/life-purchases/{lot['id']}/", {"active": False}, format="json")
    assert c.post("/api/v1/institution/current/life-purchase/", off, format="json").status_code == 200
    assert not PayrollGroup.objects.get(institution=institution, segment=Segment.COMPRA_VIDAS).active
    assert LifePurchase.objects.filter(institution=institution).count() == 1  # nunca excluído


def test_filtro_de_folhas(institution, master, client_for):
    assert segments_for_filter(institution, "COMPRA_VIDAS") == []  # inexistente sem CV
    c = client_for(master)
    enable_cv(c)
    institution.refresh_from_db()
    assert segments_for_filter(institution, "PREVIDENCIARIO") == [Segment.PREVIDENCIARIO, Segment.COMPRA_VIDAS]

    split = lambda plano: [p["massa"] for p in c.get(f"/api/v1/dashboard/?plano={plano}").json()["graficos"]["por_plano"]]  # noqa: E731
    assert split("TODOS") == ["FINANCEIRO", "PREVIDENCIARIO", "COMPRA_VIDAS"]
    assert split("PREVIDENCIARIO") == ["PREVIDENCIARIO", "COMPRA_VIDAS"]
    assert split("PREVIDENCIARIO_PROPRIO") == ["PREVIDENCIARIO"]
    assert split("COMPRA_VIDAS") == ["COMPRA_VIDAS"]


def test_base_atuarial_leiaute_sprev(institution, master, client_for):
    c = client_for(master)
    enable_cv(c)
    r = c.post("/api/v1/actuarial-bases/", {"reference_year": 2026, "reference_month": 7}, format="json")
    assert r.status_code == 201, r.json()
    base = r.json()
    assert base["data_base"] == "07/2026" and len(base["file_sha256"]) == 64
    assert any("IBGE" in p for p in base["pendencias"])
    assert any(p.startswith("Aposentados: origem não implementada") for p in base["pendencias"])

    resp = c.get(f"/api/v1/actuarial-bases/{base['id']}/download/")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(b"".join(resp.streaming_content)))
    names = set(zf.namelist())
    for folder in ("FUNDO_CAPITALIZACAO", "FUNDO_REPARTICAO", "COMPLEMENTAR_COMPRA_VIDAS"):
        assert f"{folder}/SERVIDORES.csv" in names and f"{folder}/PENS_FALEC.csv" in names
    assert {"COMPLEMENTAR_COMPRA_VIDAS/LOTES.csv", "RESUMO.csv", "PENDENCIAS.csv", "LEIA-ME.txt"} <= names
    header = zf.read("FUNDO_CAPITALIZACAO/SERVIDORES.csv").decode("utf-8-sig").splitlines()[0]
    assert header.split(";") == layouts.column_names("servidores")

    assert ActuarialBase.objects.filter(institution=institution).count() == 1
    assert AuditLog.objects.filter(module="atuarial.base", action="EXPORT").count() == 2  # geração + download


def test_base_atuarial_permissoes_e_data(institution, consulta, master, client_for):
    assert client_for(consulta).post("/api/v1/actuarial-bases/", {"reference_year": 2026, "reference_month": 7},
                                     format="json").status_code == 403
    r = client_for(master).post("/api/v1/actuarial-bases/", {"reference_year": 2999, "reference_month": 1}, format="json")
    assert r.status_code == 409
