"""CNPJ digitado com máscara (00.000.000/0000-00) é aceito e gravado só com os dígitos."""
from apps.cadastros.models import Ente


def test_ente_cnpj_com_mascara(institution, master, client_for):
    c = client_for(master)
    r = c.post("/api/v1/entes/", {"name": "Município Teste", "kind": "MUNICIPIO", "cnpj": "28.695.658/0001-84",
                                            "ibge_code": "3300407", "uf": "RJ"}, format="json")
    assert r.status_code == 201, r.json()
    assert Ente.objects.get(pk=r.json()["id"]).cnpj == "28695658000184"
    assert r.json()["cnpj_formatado"] == "28.695.658/0001-84"
    r = c.post("/api/v1/entes/", {"name": "X", "kind": "MUNICIPIO", "cnpj": "28.695.658/0001-85", "uf": "RJ"},
               format="json")
    assert r.status_code == 400 and "inválido" in str(r.json())
