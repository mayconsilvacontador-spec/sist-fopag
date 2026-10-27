"""Ficha financeira: importação (validar → gravar, sem duplicar), ficha anual, controle da contribuição e histórico."""
import io
from datetime import date
from decimal import Decimal

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cadastros.models import Ente, Organ, Position
from apps.employment.models import EmploymentLink
from apps.institutions.services import set_parameter
from apps.pessoal.ficha import suggest_category
from apps.pessoal.models import FinancialLine
from apps.previdencia.models import ContributionSalary

from .test_fase5 import cpf, person

URL = "/api/v1/ativos/ficha-financeira"
HEAD = "CPF;MATRICULA;COMPETENCIA;TIPO_FOLHA;CODIGO;RUBRICA;NATUREZA;CLASSIFICACAO;VALOR\n"


def _csv(c, rows):
    body = HEAD + "".join(f"{c};9001;{r}\n" for r in rows)
    return SimpleUploadedFile("ficha.csv", body.encode("utf-8"), content_type="text/csv")


def test_ficha_financeira_e_contribuicao(institution, master, consulta, client_for):
    set_parameter(institution, "folha.aliquota_segurado", "0.11", date(2019, 1, 1))
    set_parameter(institution, "arrecadacao.aliquota_patronal", "0.22", date(2019, 1, 1))
    organ = Organ.objects.create(institution=institution, ente=Ente.objects.create(institution=institution, name="M"), name="Prefeitura")
    p = person(institution, 600000001, "Servidor Ficha", date(1975, 1, 1))
    EmploymentLink.objects.create(institution=institution, person=p, organ=organ,
                                  position=Position.objects.create(institution=institution, name="AUX"),
                                  registration="9001", public_service_start=date(2010, 1, 1), ente_start=date(2010, 1, 1),
                                  position_start=date(2010, 1, 1))
    c = client_for(master)
    assert c.get(f"{URL}/modelo/").status_code == 200
    rows = ["03/2019;MENSAL;001;VENCIMENTO;P;;2500,00", "03/2019;MENSAL;501;CONTRIB. PREVIDENCIARIA IPREV;D;;275,00",
            "03/2019;MENSAL;900;BASE PREVIDENCIA;B;BASE_RPPS;2500,00",
            "04/2019;MENSAL;001;VENCIMENTO;P;;2500,00", "04/2019;MENSAL;501;CONTRIB. PREVIDENCIARIA IPREV;D;;200,00",
            "04/2019;MENSAL;900;BASE PREVIDENCIA;B;BASE_RPPS;2500,00",
            "12/2019;DECIMO;001;VENCIMENTO;P;;2500,00", "13/2019;MENSAL;001;X;P;;1,00"]
    cpf_ = cpf(600000001)
    assert client_for(consulta).post(f"{URL}/importar/", {"file": _csv(cpf_, rows)}, format="multipart").status_code == 403
    prev = c.post(f"{URL}/importar/", {"file": _csv(cpf_, rows)}, format="multipart").json()
    assert prev["gravado"] is False and prev["total_erros"] == 1 and not FinancialLine.objects.exists()
    rub = {r["codigo"]: r["classificacao"] for r in prev["rubricas"]}
    assert rub["501"] == "CONTRIB_RPPS"  # sugerido pelo nome
    r = c.post(f"{URL}/importar/", {"file": _csv(cpf_, rows), "confirmar": "1", "pessoa": str(p.pk)}, format="multipart").json()
    assert r["gravado"] and r["incluidas"] == 7
    r = c.post(f"{URL}/importar/", {"file": _csv(cpf_, rows), "confirmar": "1"}, format="multipart").json()
    assert r["incluidas"] == 0 and r["atualizadas"] == 7 and FinancialLine.objects.count() == 7  # não duplica

    f = c.get(f"{URL}/{p.pk}/", {"ano": 2019}).json()
    venc = next(ln for ln in f["linhas"] if ln["codigo"] == "001")
    assert venc["valores"]["3"] == "2500.00" and venc["valores"]["13"] == "2500.00" and venc["total"] == "7500.00"
    assert f["totais"]["CONTRIB_RPPS"]["total"] == "475.00"
    x = c.get(f"{URL}/{p.pk}/excel/", {"ano": 2019})
    assert x.status_code == 200 and openpyxl.load_workbook(io.BytesIO(x.content)).active["A1"].value.startswith("FICHA")

    ctr = c.get(f"{URL}/{p.pk}/contribuicoes/").json()
    abr = next(i for i in ctr["competencias"] if i["competencia"] == "04/2019")
    assert abr["devido"] == "275.00" and abr["diferenca"] == "-75.00" and "descontado a menor" in abr["avisos"]
    assert abr["patronal"] == "550.00" and abr["repasse_orgao"]["situacao"] == "Sem guia lançada"
    assert Decimal(ctr["totais"]["descontado"]) == Decimal("475.00")

    ContributionSalary.objects.create(institution=institution, person=p, competence=date(2019, 3, 1), amount=Decimal("1"))
    h = c.post(f"{URL}/{p.pk}/historico/").json()
    assert h == {"incluidos": 1, "ja_existiam": 1}
    assert ContributionSalary.objects.get(person=p, competence=date(2019, 3, 1)).amount == Decimal("1.00")  # mantido

    assert c.post(f"{URL}/classificar/", {"codigo": "501", "classificacao": ""}, format="json").json()["linhas"] == 2


def test_sugestao_de_classificacao():
    assert suggest_category("DESC. PREVIDENCIA MUNICIPAL", "DESCONTO") == "CONTRIB_RPPS"
    assert suggest_category("INSS", "DESCONTO") == ""
    assert suggest_category("IRRF", "DESCONTO") == "IRRF"
    assert suggest_category("PATRONAL RPPS", "BASE") == "PATRONAL"


def test_aliquotas_e_lancamento_manual(institution, master, consulta, client_for):
    c = client_for(master)
    url = "/api/v1/arrecadacao/aliquotas/"
    ok = {"tipo": "SERVIDOR", "percentual": "14", "inicio": "09/2025", "fundamento": "ELOM 28/2025"}
    assert client_for(consulta).post(url, ok, format="json").status_code == 403
    assert c.post(url, ok, format="json").status_code == 201
    # vigência histórica (antes da primeira) e nova
    assert c.post(url, {**ok, "percentual": "11", "inicio": "01/2004", "fundamento": "Lei antiga"}, format="json").status_code == 201
    assert c.post(url, {**ok, "percentual": "12", "inicio": "01/2010", "fundamento": "x"}, format="json").status_code == 409
    assert c.post(url, {**ok, "percentual": "0", "inicio": "01/2027"}, format="json").status_code == 409
    serv = next(x for x in c.get(url).json() if x["tipo"] == "SERVIDOR")
    assert [v["percentual"] for v in serv["vigencias"]] == ["14", "11"] and serv["vigencias"][1]["fim"] == "2025-08-31"
    assert c.get(url, {"competencia": "03/2019"}).json()["servidor"] == "11"

    p = person(institution, 600000002, "Servidor Manual", date(1975, 1, 1))
    r = c.post(f"{URL}/{p.pk}/lancar/", {"competencia": "05/2019", "base": "3000,00"}, format="json")
    assert r.status_code == 201 and r.json()["descontado"] == "330.00" and r.json()["historico"] is True
    c.post(f"{URL}/{p.pk}/lancar/", {"competencia": "06/2019", "base": "3000", "descontado": "300"}, format="json")
    ContributionSalary.objects.create(institution=institution, person=p, competence=date(2019, 7, 1), amount=Decimal("3000"))
    ctr = {i["competencia"]: i for i in c.get(f"{URL}/{p.pk}/contribuicoes/").json()["competencias"]}
    assert ctr["05/2019"]["diferenca"] == "0.00" and ctr["06/2019"]["diferenca"] == "-30.00"
    assert ctr["07/2019"]["fonte"] == "HISTORICO" and "desconto não informado" in ctr["07/2019"]["avisos"][0]
