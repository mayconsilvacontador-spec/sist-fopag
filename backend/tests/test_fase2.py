import io
import zipfile
from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.alerts.checks import CHECKS
from apps.cadastros.models import Ente, Organ, Position
from apps.employment.models import FunctionalEvent
from apps.institutions.models import Institution
from apps.people.models import Address, Person
from apps.protocolo import deadlines
from apps.protocolo.models import Holiday, Process, Sector

from .conftest import make_user

CPF_A, CPF_B, CPF_C = "52998224725", "11144477735", "39053344705"


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def base(institution):
    ente = Ente.objects.create(institution=institution, name="Município de Teste")
    organ = Organ.objects.create(institution=institution, ente=ente, name="Prefeitura de Teste", sigfis_code="1234")
    position = Position.objects.create(institution=institution, name="Professor", career="Magistério", cargo_type=2)
    return {"organ": organ, "position": position}


def person_body(cpf=CPF_A, **extra):
    return {"cpf": cpf, "name": "Maria da Silva", "birth_date": "1970-05-10", "sex": 1, "marital_status": 2, **extra}


# --------------------------------------------------------------------------- prazos
def test_feriados_e_contagem_de_prazos():
    hol = frozenset(d for d, _, _ in deadlines.national_holidays(2026))
    assert date(2026, 4, 3) in hol  # Sexta-feira Santa (Páscoa em 05/04/2026)
    assert date(2026, 11, 20) in hol
    # Sexta 30/10/2026 + 3 dias úteis: seg 02/11 é Finados -> 03, 04, 05/11
    assert deadlines.add_days(date(2026, 10, 30), 3, True, hol) == date(2026, 11, 5)
    # Corridos: 30/10 + 2 = 01/11 (domingo) -> 02/11 feriado -> prorroga para 03/11
    assert deadlines.add_days(date(2026, 10, 30), 2, False, hol) == date(2026, 11, 3)
    assert deadlines.count_days(date(2026, 10, 30), date(2026, 11, 5), True, hol) == 3


# --------------------------------------------------------------------------- Cadastro Único
def test_cadastro_unico_cpf_e_historico_de_endereco(institution, master, client_for):
    c = client_for(master)
    assert c.post("/api/v1/people/", person_body(cpf="12345678900"), format="json").status_code == 400
    r = c.post("/api/v1/people/", person_body(cpf="529.982.247-25"), format="json")
    assert r.status_code == 201, r.json()
    pid = r.json()["id"]
    assert c.post("/api/v1/people/", person_body(), format="json").status_code == 400  # CPF duplicado
    assert c.get(f"/api/v1/people/by-cpf/?cpf={CPF_A}").json()["id"] == pid

    addr = {"person": pid, "street": "Rua A", "city": "Barra Mansa", "uf": "RJ", "valid_from": "2020-01-01"}
    assert c.post("/api/v1/addresses/", addr, format="json").status_code == 201
    assert c.post("/api/v1/addresses/", {**addr, "street": "Rua B", "valid_from": "2025-03-01"},
                  format="json").status_code == 201
    old = Address.objects.get(street="Rua A")
    assert old.valid_to == date(2025, 2, 28)  # vigência encerrada, não sobrescrita
    assert c.post("/api/v1/addresses/", {**addr, "valid_from": "2024-01-01"}, format="json").status_code == 409


def test_dependentes_e_documentos(institution, master, client_for):
    c = client_for(master)
    holder = c.post("/api/v1/people/", person_body(), format="json").json()["id"]
    child = c.post("/api/v1/people/", person_body(cpf=CPF_B, name="Filho", birth_date="2015-01-01", sex=2),
                   format="json").json()["id"]
    dep = {"holder": holder, "dependent": child, "kind": 3, "start_date": "2015-01-01"}
    assert c.post("/api/v1/dependencies/", {**dep, "kind": 4}, format="json").status_code == 409  # não é inválido
    assert c.post("/api/v1/dependencies/", dep, format="json").status_code == 201
    assert c.post("/api/v1/dependencies/", dep, format="json").status_code in (400, 409)

    pdf = SimpleUploadedFile("rg.pdf", b"%PDF-1.4 teste", content_type="application/pdf")
    r = c.post("/api/v1/documents/", {"person": holder, "doc_type": "IDENTIDADE", "file": pdf}, format="multipart")
    assert r.status_code == 201 and r.json()["version"] == 1
    pdf2 = SimpleUploadedFile("rg2.pdf", b"%PDF-1.4 versao 2", content_type="application/pdf")
    r2 = c.post("/api/v1/documents/", {"person": holder, "doc_type": "IDENTIDADE", "file": pdf2}, format="multipart")
    assert r2.json()["version"] == 2
    fake = SimpleUploadedFile("x.pdf", b"nao e pdf", content_type="application/pdf")
    assert c.post("/api/v1/documents/", {"person": holder, "doc_type": "CPF", "file": fake},
                  format="multipart").status_code == 409


# --------------------------------------------------------------------------- vínculos + atuarial
def test_vinculo_validacoes_encerramento_e_base_atuarial(institution, master, client_for, base):
    c = client_for(master)
    pid = c.post("/api/v1/people/", person_body(pis_pasep="12345678901"), format="json").json()["id"]
    child = c.post("/api/v1/people/", person_body(cpf=CPF_B, name="Filho", birth_date="2015-01-01", sex=2),
                   format="json").json()["id"]
    c.post("/api/v1/dependencies/", {"holder": pid, "dependent": child, "kind": 3, "start_date": "2015-01-01"},
           format="json")
    link = {"person": pid, "organ": str(base["organ"].pk), "position": str(base["position"].pk),
            "registration": "1001", "public_service_start": "1995-03-01", "ente_start": "1995-03-01",
            "position_start": "1995-03-01", "segment": "FINANCEIRO"}
    assert c.post("/api/v1/employment-links/", {**link, "ente_start": "1990-01-01"}, format="json").status_code == 400
    assert c.post("/api/v1/employment-links/", {**link, "segment": "COMPRA_VIDAS"}, format="json").status_code == 400
    r = c.post("/api/v1/employment-links/", link, format="json")
    assert r.status_code == 201, r.json()
    assert c.get("/api/v1/people/?tipo=servidor").json()["count"] == 1

    base_r = c.post("/api/v1/actuarial-bases/", {"reference_year": 2026, "reference_month": 7}, format="json").json()
    assert base_r["summary"]["FUNDO_REPARTICAO"]["SERVIDORES"] == 1
    assert base_r["summary"]["FUNDO_REPARTICAO"]["DEPENDENTES"] == 1
    zf = zipfile.ZipFile(io.BytesIO(b"".join(c.get(f"/api/v1/actuarial-bases/{base_r['id']}/download/").streaming_content)))
    lines = zf.read("FUNDO_REPARTICAO/SERVIDORES.csv").decode("utf-8-sig").splitlines()
    header, row = lines[0].split(";"), lines[1].split(";")
    data = dict(zip(header, row))
    assert data["ID_SERVIDOR_CPF"] == "529.982.247-25" and data["CO_TIPO_FUNDO"] == "2"
    assert data["DT_ING_SERV_PUB"] == "01/03/1995" and data["NU_DEPENDENTES"] == "1"

    lid = r.json()["id"]
    closed = c.post(f"/api/v1/employment-links/{lid}/close/",
                    {"status": "EXONERADO", "end_date": "2026-06-30", "end_reason": "Exoneração a pedido"}, format="json")
    assert closed.status_code == 200 and closed.json()["status"] == "EXONERADO"
    assert FunctionalEvent.objects.filter(link_id=lid, event_type="EXONERACAO").exists()
    assert c.patch(f"/api/v1/employment-links/{lid}/", {"class_level": "A"}, format="json").status_code == 409


# --------------------------------------------------------------------------- protocolo
def test_protocolo_tramitacao_prazos_e_alertas(institution, master, client_for):
    c = client_for(master)
    other = make_user(institution, "atendente", "CONSULTA")
    s1 = Sector.objects.create(institution=institution, name="Protocolo Geral", code="PROT")
    s1.members.add(master)
    s2 = Sector.objects.create(institution=institution, name="Benefícios", code="BEN")
    tipo = c.post("/api/v1/protocol/process-types/", {"name": "Aposentadoria", "deadline_days": 10},
                  format="json").json()
    body = {"process_type": tipo["id"], "sector": str(s1.pk), "subject": "Pedido de aposentadoria",
            "interested_name": "Maria"}
    p1 = c.post("/api/v1/protocol/processes/", body, format="json")
    assert p1.status_code == 201, p1.json()
    p2 = c.post("/api/v1/protocol/processes/", body, format="json").json()
    assert p1.json()["code"].startswith("000001/") and p2["code"].startswith("000002/")
    pid = p1.json()["id"]

    send = {"to_sector": str(s2.pk), "text": "Encaminho para análise do benefício."}
    assert c.post(f"/api/v1/protocol/processes/{pid}/send/", {**send, "text": "curto"}, format="json").status_code == 409
    assert c.post(f"/api/v1/protocol/processes/{pid}/send/", send, format="json").status_code == 200
    # Usuário fora do setor e sem perfil de gestão não recebe
    s2.members.add(other)
    assert client_for(other).post(f"/api/v1/protocol/processes/{pid}/receive/").status_code == 403  # CONSULTA não edita
    r = c.post(f"/api/v1/protocol/processes/{pid}/receive/")
    assert r.status_code == 200 and r.json()["pending_receipt"] is False

    due = date.fromisoformat(r.json()["due_date"])
    proc = Process.objects.get(pk=pid)
    c.post(f"/api/v1/protocol/processes/{pid}/suspend/", {"text": "Aguardando certidão do INSS."}, format="json")
    proc.refresh_from_db()
    proc.suspended_since = timezone.localdate() - timedelta(days=7)
    proc.save()
    resumed = c.post(f"/api/v1/protocol/processes/{pid}/resume/", {"text": "Certidão recebida, retomando."},
                     format="json").json()
    assert date.fromisoformat(resumed["due_date"]) > due  # prazo estendido pelo sobrestamento

    proc.refresh_from_db()
    proc.due_date = timezone.localdate() - timedelta(days=1)
    proc.save()
    assert any(s.key == str(proc.pk) for s in CHECKS["PROTOCOLO_PRAZO_VENCIDO"](institution))
    moves = [m["kind"] for m in c.get(f"/api/v1/protocol/processes/{pid}/movements/").json()]
    assert moves == ["ABERTURA", "ENVIO", "RECEBIMENTO", "SOBRESTAMENTO", "RETOMADA"]

    assert c.post("/api/v1/protocol/holidays/generate/", {"year": 2026}, format="json").json()["criados"] == 13
    assert Holiday.objects.filter(institution=institution, date=date(2026, 4, 3)).exists()


# --------------------------------------------------------------------------- tipo de órgão
def test_tipo_de_orgao_oculta_modulos_de_rpps(institution, master, client_for):
    c = client_for(master)
    assert "atuarial.base:visualizar" in c.get("/api/v1/auth/me/").json()["permissions"]
    Institution.objects.filter(pk=institution.pk).update(kind="PREFEITURA")
    perms = c.get("/api/v1/auth/me/").json()["permissions"]
    assert "atuarial.base:visualizar" not in perms and "protocolo.processos:incluir" in perms
    assert c.get("/api/v1/actuarial-bases/").status_code == 403
    assert Person.objects.count() == 0
