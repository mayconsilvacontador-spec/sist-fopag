"""Legislação de cada RPPS: normas (com PDF), pacotes-modelo de regras e nada de citação fixa de um ente."""
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.institutions.services import get_parameter
from apps.previdencia.legislacao import main_norm
from apps.previdencia.models import LegalNorm, RetirementRule

URL = "/api/v1/previdencia"


def test_normas_e_pacotes(institution, master, consulta, client_for):
    c = client_for(master)
    pdf = SimpleUploadedFile("lc.pdf", b"%PDF-1.4 norma ficticia", content_type="application/pdf")
    r = c.post(f"{URL}/legislacao/", {"kind": "LEI_COMPLEMENTAR", "number": "45", "date": "2021-12-20",
                                      "valid_from": "2022-01-01", "summary": "Reforma da previdência municipal (fictícia)",
                                      "subjects": ["APOSENTADORIA", "PENSAO"], "file": pdf}, format="multipart")
    assert r.status_code == 201, r.json()
    norma = r.json()
    assert norma["citation"] == "Lei Complementar nº 45, de 20 de dezembro de 2021" and norma["has_file"]
    assert c.get(f"{URL}/legislacao/{norma['id']}/arquivo/").status_code == 200
    bad = SimpleUploadedFile("x.pdf", b"nao e pdf", content_type="application/pdf")
    assert c.post(f"{URL}/legislacao/", {"kind": "LEI", "number": "1", "file": bad}, format="multipart").status_code == 409
    assert client_for(consulta).post(f"{URL}/legislacao/", {"kind": "LEI", "number": "2"}, format="multipart").status_code == 403
    assert main_norm(institution).number == "45"

    # ente SEM reforma: regras antigas valendo, sem data de corte
    assert client_for(consulta).post(f"{URL}/pacotes-regras/", {"pacote": "SEM_REFORMA"}, format="json").status_code == 403
    assert c.post(f"{URL}/pacotes-regras/", {"pacote": "SEM_REFORMA", "justificativa": "curta"}, format="json").status_code == 409
    r = c.post(f"{URL}/pacotes-regras/", {"pacote": "SEM_REFORMA", "justificativa": "Implantação do RPPS sem reforma"},
               format="json")
    assert r.status_code == 200, r.json()
    regras = RetirementRule.objects.filter(institution=institution, active=True)
    assert regras.count() == 8 and not regras.exclude(valid_to=None).exists()
    assert not any("LOM 28" in x.legal_basis for x in regras)
    assert regras.get(code="EC41_ART6").group == "TRANSICAO" and regras.get(code="CF40_IIIA").group == "PERMANENTE"

    # depois o ente aprova reforma adotando a EC 103: regras antigas viram direito adquirido; novas citam a lei local
    r = c.post(f"{URL}/pacotes-regras/", {"pacote": "EC103", "reforma": "2022-01-01", "norma": norma["id"],
                                          "justificativa": "LC 45/2021 — reforma da previdência local"}, format="json")
    assert r.status_code == 200, r.json()
    res = r.json()
    assert res["atualizadas"] == 8 and res["criadas"] == 8 and res["inativadas"] == 0
    old = RetirementRule.objects.get(institution=institution, code="CF40_IIIA")
    assert old.valid_to == date(2021, 12, 31) and old.package == "EC103"
    perm = RetirementRule.objects.get(institution=institution, code="EC103_ART10_I")
    assert perm.legal_basis.endswith("c/c Lei Complementar nº 45, de 20 de dezembro de 2021") and perm.norm_id
    assert str(get_parameter(institution, "previdencia.vigencia_reforma_local"))[:10] == "2022-01-01"
    info = c.get(f"{URL}/pacotes-regras/").json()
    assert info["pacote_atual"] == "EC103" and len(info["pacotes"]) == 3

    # voltar a SEM_REFORMA inativa (não apaga) as regras da EC 103
    r = c.post(f"{URL}/pacotes-regras/", {"pacote": "SEM_REFORMA", "justificativa": "Teste de troca de pacote"}, format="json")
    assert r.json()["inativadas"] == 8 and RetirementRule.objects.filter(institution=institution).count() == 16

    # inativar norma
    assert c.post(f"{URL}/legislacao/{norma['id']}/inativar/").json()["active"] is False
    assert LegalNorm.objects.get(pk=norma["id"]).rules.count() > 0
