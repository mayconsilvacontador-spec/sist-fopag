import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.actuarial import layouts
from apps.employment.models import EmploymentLink
from apps.people import receita
from apps.people.models import Dependency, LegacyBenefit, Person

SERV_CPF, DEP_CPF, APOS_CPF, INST_CPF, PENS_CPF = "52998224725", "11144477735", "39053344705", "15350946056", "71428793860"


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def csv_file(key, rows, name):
    header = layouts.column_names(key)
    lines = [";".join(header)] + [";".join(str(r.get(c, "")) for c in header) for r in rows]
    return SimpleUploadedFile(name, ("\r\n".join(lines)).encode("utf-8-sig"), content_type="text/csv")


COMMON = {"NU_ANO": 2026, "NU_MES": 7, "CO_IBGE": "3300407", "NO_ENTE": "Município de Teste", "SG_UF": "RJ",
          "CO_COMP_MASSA": 1, "NO_ORGAO": "Prefeitura de Teste", "CO_PODER": 1, "CO_TIPO_PODER": 1}


def files():
    serv = csv_file("servidores", [
        {**COMMON, "CO_TIPO_FUNDO": 2, "NU_CNPJ_ORGAO": "", "CO_TIPO_CARGO": 2, "ID_SERVIDOR_MATRICULA": "777",
         "ID_SERVIDOR_CPF": "529.982.247-25", "CO_SEXO_SERVIDOR": 1, "CO_EST_CIVIL_SERVIDOR": 2,
         "DT_NASC_SERVIDOR": "10/05/1970", "CO_SITUACAO_FUNCIONAL": 1, "CO_TIPO_VINCULO": 1,
         "DT_ING_SERV_PUB": "01/03/1995", "DT_ING_ENTE": "01/03/1995", "DT_ING_CARGO": "01/03/1995",
         "NO_CARGO": "Professor", "NO_CARREIRA": "Magistério", "VL_BASE_CALCULO": "4.321,00", "IN_ABONO_PERMANENCIA": 2},
        {**COMMON, "CO_TIPO_FUNDO": 1, "ID_SERVIDOR_MATRICULA": "778", "ID_SERVIDOR_CPF": "12345678900",
         "CO_SEXO_SERVIDOR": 2, "DT_NASC_SERVIDOR": "01/01/1980", "DT_ING_SERV_PUB": "01/01/2005", "NO_CARGO": "Gari"},
    ], "SERVIDORES.csv")
    deps = csv_file("dependentes", [
        {**COMMON, "CO_TIPO_FUNDO": 2, "ID_SEGURADO_MATRICULA": "777", "ID_SEGURADO_CPF": SERV_CPF,
         "CO_SEXO_SEGURADO": 1, "ID_DEPENDENTE": DEP_CPF, "ID_DEPENDENTE_CPF": DEP_CPF,
         "DT_NASC_DEPENDENTE": "01/01/2010", "CO_SEXO_DEPENDENTE": 2, "CO_CONDICAO_DEPENDENTE": 1,
         "CO_TIPO_DEPENDECIA": 3},
    ], "DEPENDENTES.csv")
    apos = csv_file("aposentados", [
        {**COMMON, "CO_TIPO_FUNDO": 1, "ID_APOSENTADO_MATRICULA": "500", "ID_APOSENTADO_CPF": APOS_CPF,
         "CO_SEXO_APOSENTADO": 2, "DT_NASC_APOSENTADO": "02/02/1955", "DT_INICIO_APOSENTADORIA": "01/01/2015",
         "VL_APOSENTADORIA": "3.500,50", "CO_CONDICAO_APOSENTADO": 1},
    ], "APOSENTADOS.csv")
    pens = csv_file("pensionistas", [
        {**COMMON, "CO_TIPO_FUNDO": 1, "ID_INSTITUIDOR_CPF": INST_CPF, "CO_SEXO_INSTITUIDOR": 2,
         "DT_NASC_INSTITUIDOR": "03/03/1950", "DT_OBITO_INSTITUIDOR": "10/10/2020", "ID_PENSIONISTA_CPF": PENS_CPF,
         "CO_SEXO_PENSIONISTA": 1, "DT_NASC_PENSIONISTA": "04/04/1952", "DT_INICIO_PENSAO": "10/10/2020",
         "VL_BENEF_PENSAO": "2000,00", "CO_CONDICAO": 1},
    ], "PENSIONISTAS.csv")
    return [deps, serv, apos, pens]  # ordem embaralhada: o importador ordena


def test_importacao_sprev_valida_sem_gravar_e_confirma(institution, master, client_for):
    c = client_for(master)
    r = c.post("/api/v1/imports/", {"files": files(), "source_system": "Sistema Antigo X"}, format="multipart")
    assert r.status_code == 201, r.json()
    batch = r.json()
    rep = batch["report"]
    assert rep["resumo"]["vinculos"] == 1 and rep["resumo"]["dependencias"] == 1 and rep["resumo"]["beneficios"] == 2
    assert rep["total_erros"] == 1 and "CPF inválido" in rep["erros"][0]["mensagem"]
    assert "*" in rep["erros"][0]["cpf"]  # CPF mascarado no relatório
    assert Person.objects.count() == 0 and EmploymentLink.objects.count() == 0  # validação não grava

    ok = c.post(f"/api/v1/imports/{batch['id']}/confirm/")
    assert ok.status_code == 200 and ok.json()["status"] == "IMPORTADO"
    link = EmploymentLink.objects.get(registration="777")
    assert link.segment == "FINANCEIRO" and link.position.name == "Professor" and link.organ.name == "Prefeitura de Teste"
    assert link.person.name == "" and link.person.sex == 1
    assert Dependency.objects.get(dependent__cpf=DEP_CPF).start_date.isoformat() == "2010-01-01"
    pens = LegacyBenefit.objects.get(kind="PENSAO")
    assert str(pens.amount) == "2000.00" and pens.instituidor.death_date.isoformat() == "2020-10-10"
    assert c.post(f"/api/v1/imports/{batch['id']}/confirm/").status_code == 409  # não importa duas vezes

    # Reimportação: pessoas existentes não são duplicadas; vínculo existente é ignorado
    r2 = c.post("/api/v1/imports/", {"files": files()[1:2], "source_system": "Sistema Antigo X"}, format="multipart").json()
    assert r2["report"]["resumo"]["vinculos_existentes"] == 1 and r2["report"]["resumo"]["pessoas_novas"] == 0
    assert c.get("/api/v1/people/?sem_nome=1").json()["count"] == 5


def test_receita_nao_configurada_e_conversao(institution, master, client_for, settings, monkeypatch):
    c = client_for(master)
    assert c.get(f"/api/v1/people/receita/?cpf={SERV_CPF}").status_code == 409  # sem credenciais
    assert c.get("/api/v1/auth/me/").json()["integracoes"]["receita"] is False

    settings.CONECTA_CLIENT_ID, settings.CONECTA_CLIENT_SECRET = "id", "segredo"
    master.cpf = "39053344705"
    master.save()
    calls = []

    def fake_request(url, data, headers):
        calls.append((url, headers))
        if url.endswith("/oauth2/jwt-token"):
            return json.dumps({"access_token": "tok", "expires_in": 7200}).encode()
        assert json.loads(data) == {"listaCpf": [SERV_CPF]}
        return json.dumps([{"Cpf": SERV_CPF, "Nome": "MARIA DA SILVA", "Sexo": 2, "DataNascimento": "19700510",
                            "NomeMae": "ANA", "UF": "RJ", "Cep": 27330000, "Municipio": "BARRA MANSA"}]).encode()

    monkeypatch.setattr(receita, "_request", fake_request)
    r = c.get(f"/api/v1/people/receita/?cpf={SERV_CPF}")
    assert r.status_code == 200, r.json()
    d = r.json()
    assert d["name"] == "MARIA DA SILVA" and d["sex"] == 1  # Receita 2 (feminino) -> SPREV 1
    assert d["birth_date"] == "1970-05-10" and d["endereco"]["cep"] == "27330000"
    assert calls[-1][1]["x-cpf-usuario"] == "39053344705"
