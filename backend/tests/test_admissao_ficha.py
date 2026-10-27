"""Admissão (pessoa + vínculo + nomeação/posse + endereço + conta), ficha com cronologia, foto e pastas de documentos."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cadastros.models import Bank, Ente, Organ, Position
from apps.employment.models import EmploymentLink

from .test_fase5 import cpf

URL = "/api/v1/people"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _payload(inst, registration="7001"):
    organ = Organ.objects.filter(institution=inst).first() or Organ.objects.create(
        institution=inst, ente=Ente.objects.create(institution=inst, name="Município"), name="Prefeitura (fictícia)")
    pos = Position.objects.filter(institution=inst).first() or Position.objects.create(institution=inst, name="PROFESSOR")
    bank = Bank.objects.filter(institution=inst).first() or Bank.objects.create(institution=inst, code="001", name="Banco Fictício")
    return {
        "pessoa": {"cpf": cpf(500000001), "name": "Servidora Admitida", "birth_date": "1990-03-10", "sex": 2},
        "vinculo": {"organ": str(organ.pk), "position": str(pos.pk), "registration": registration,
                    "nomeacao": "2026-02-01", "exercicio": "2026-02-10", "base_salary": "3.500,00", "class_level": "A",
                    "act_number": "123/2026"},
        "endereco": {"street": "Rua Fictícia", "number": "10", "city": "Serra Azul do Sul", "uf": "RJ"},
        "conta": {"bank": str(bank.pk), "branch": "1234", "account": "98765", "account_digit": "0"},
    }


def test_admissao_ficha_cronologia_foto(institution, master, consulta, client_for):
    c = client_for(master)
    data = _payload(institution)
    assert client_for(consulta).post(f"{URL}/admissao/", data, format="json").status_code == 403
    r = c.post(f"{URL}/admissao/", data, format="json")
    assert r.status_code == 201, r.json()
    pid = r.json()["pessoa"]
    link = EmploymentLink.objects.get(pk=r.json()["vinculo"])
    assert str(link.base_salary) == "3500.00" and link.ente_start.isoformat() == "2026-02-10"
    assert {e.event_type for e in link.events.all()} == {"NOMEACAO", "POSSE"}
    # mesma matrícula no mesmo órgão é recusada
    assert c.post(f"{URL}/admissao/", data, format="json").status_code == 409
    # 2º vínculo da mesma pessoa (acumulação): reaproveita o Cadastro Único
    r2 = c.post(f"{URL}/admissao/", _payload(institution, "7002"), format="json").json()
    assert r2["pessoa"] == pid and r2["pessoa_nova"] is False

    ficha = c.get(f"{URL}/{pid}/ficha/").json()
    assert ficha["situacao"] == "Ativo" and ficha["vinculo_ativo"]["vencimento"]["valor"] == "3500.00"
    tl = c.get(f"{URL}/{pid}/cronologia/").json()
    titles = [e["titulo"] for e in tl]
    assert titles[0] == "Nascimento" and "Nomeação / admissão" in titles and "Posse / exercício" in titles

    # foto: só imagem de verdade; consulta não altera
    fake = SimpleUploadedFile("x.png", b"<svg></svg>", content_type="image/png")
    assert c.post(f"{URL}/{pid}/foto/", {"file": fake}, format="multipart").status_code == 409
    up = SimpleUploadedFile("f.png", PNG, content_type="image/png")
    assert client_for(consulta).post(f"{URL}/{pid}/foto/", {"file": up}, format="multipart").status_code == 403
    up = SimpleUploadedFile("f.png", PNG, content_type="image/png")
    assert c.post(f"{URL}/{pid}/foto/", {"file": up}, format="multipart").status_code == 200
    got = c.get(f"{URL}/{pid}/foto/")
    assert got.status_code == 200 and got["Content-Type"] == "image/png"

    # pastas de documentos
    pdf = io.BytesIO(b"%PDF-1.4\n%ficticio\n")
    pdf.name = "portaria.pdf"
    r = c.post("/api/v1/documents/", {"person": pid, "doc_type": "NOMEACAO", "file": pdf}, format="multipart")
    assert r.status_code == 201, r.json()
    assert r.json()["pasta"] == "FUNCIONAIS"
