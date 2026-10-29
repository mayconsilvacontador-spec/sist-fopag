"""Base do RPPS: cálculo inverso (desconto ÷ alíquota) × rubricas que entram na base, e relatórios do DIPR."""
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cadastros.models import Ente, Organ, Position
from apps.employment.models import EmploymentLink
from apps.institutions.services import set_parameter
from apps.people.models import Dependency

from .test_fase5 import cpf, person

URL = "/api/v1/ativos/ficha-financeira"
HEAD = "CPF;MATRICULA;COMPETENCIA;TIPO_FOLHA;CODIGO;RUBRICA;NATUREZA;CLASSIFICACAO;VALOR\n"


def test_base_pelas_rubricas_e_dipr(institution, master, consulta, client_for):
    set_parameter(institution, "folha.aliquota_segurado", "0.11", date(2019, 1, 1))
    set_parameter(institution, "arrecadacao.aliquota_patronal", "0.22", date(2019, 1, 1))
    ente = Ente.objects.create(institution=institution, name="M")
    org_a = Organ.objects.create(institution=institution, ente=ente, name="Prefeitura", short_name="PREF")
    org_b = Organ.objects.create(institution=institution, ente=ente, name="Câmara", short_name="CAM")
    pos = Position.objects.create(institution=institution, name="AUX")
    p1 = person(institution, 600000021, "Servidor Um", date(1980, 1, 1))
    p2 = person(institution, 600000022, "Servidor Dois", date(1981, 1, 1))
    filho = person(institution, 600000023, "Filho Um", date(2015, 1, 1), account=False)
    Dependency.objects.create(institution=institution, holder=p1, dependent=filho, kind=3, start_date=date(2015, 1, 1))
    for p, org, reg in ((p1, org_a, "100"), (p2, org_b, "200")):
        EmploymentLink.objects.create(institution=institution, person=p, organ=org, position=pos, registration=reg,
                                      public_service_start=date(2010, 1, 1), ente_start=date(2010, 1, 1),
                                      position_start=date(2010, 1, 1), segment="PREVIDENCIARIO")
    c1, c2 = cpf(600000021), cpf(600000022)
    rows = [  # março: desconto certo (11% do vencimento); abril: desconto também sobre a gratificação (errado)
        f"{c1};100;03/2019;MENSAL;1;VENCIMENTO;P;;1000,00", f"{c1};100;03/2019;MENSAL;9;GRATIFICACAO;P;;200,00",
        f"{c1};100;03/2019;MENSAL;3;DESCONTO PREVIDENCIA;D;;110,00",
        f"{c1};100;04/2019;MENSAL;1;VENCIMENTO;P;;1000,00", f"{c1};100;04/2019;MENSAL;9;GRATIFICACAO;P;;200,00",
        f"{c1};100;04/2019;MENSAL;3;DESCONTO PREVIDENCIA;D;;132,00",
        f"{c1};100;05/2019;MENSAL;1;VENCIMENTO;P;;1000,00", f"{c1};100;05/2019;MENSAL;3;DESCONTO PREVIDENCIA;D;;110,00",
        f"{c2};200;03/2019;MENSAL;1;VENCIMENTO;P;;2000,00", f"{c2};200;03/2019;MENSAL;3;DESCONTO PREVIDENCIA;D;;220,00",
    ]
    c = client_for(master)
    f = SimpleUploadedFile("f.csv", (HEAD + "\n".join(rows)).encode(), content_type="text/csv")
    assert c.post(f"{URL}/importar/", {"file": f, "confirmar": "1"}, format="multipart").json()["gravado"]

    # cálculo inverso: base = desconto ÷ alíquota
    contrib = {i["competencia"]: i for i in c.get(f"{URL}/{p1.pk}/contribuicoes/").json()["competencias"]}
    assert contrib["04/2019"]["base"] == "1200.00" and contrib["04/2019"]["base_origem"] == "DESCONTO"

    # descoberta: vencimento sempre na base; gratificação só em 1 de 2 → não sugerida
    d = c.get(f"{URL}/{p1.pk}/descobrir-base/").json()
    sug = {r["codigo"]: r for r in d["rubricas"]}
    assert d["resolvidas"] == 3 and sug["1"]["sugere"] and not sug["9"]["sugere"] and sug["9"]["percentual"] == 50
    assert client_for(consulta).post(f"{URL}/{p1.pk}/descobrir-base/", {"codigos": ["1"]}, format="json").status_code == 403
    assert c.post(f"{URL}/{p1.pk}/descobrir-base/", {"codigos": ["1"]}, format="json").json()["linhas"] == 3

    # comparação: abril foi descontado sobre R$ 1.200 mas a base é R$ 1.000 → descontado a maior
    contrib = {i["competencia"]: i for i in c.get(f"{URL}/{p1.pk}/contribuicoes/").json()["competencias"]}
    abr = contrib["04/2019"]
    assert abr["base"] == "1000.00" and abr["base_origem"] == "RUBRICAS" and abr["base_pelo_desconto"] == "1200.00"
    assert Decimal(abr["diferenca"]) == Decimal("22.00") and any("descontado a maior" in a for a in abr["avisos"])
    assert not contrib["03/2019"]["avisos"]

    # DIPR analítico: por órgão, subtotal, bruto, base, nº de servidores e dependentes
    r = c.get("/api/v1/reports/dipr-analitico/?competencia=2019-03").json()
    linhas = r["linhas"]
    assert [x["nome"] for x in linhas if x.get("_subtotal")] == ["SUBTOTAL — 1 segurado(s)"] * 2
    um = next(x for x in linhas if x["nome"] == "Servidor Um")
    assert um["orgao"] == "PREF" and Decimal(um["bruto"]) == Decimal("1200") and Decimal(um["base"]) == Decimal("1000")
    assert um["dependentes"] == 1 and Decimal(um["patronal"]) == Decimal("220.00")
    dois = next(x for x in linhas if x["nome"] == "Servidor Dois")
    assert Decimal(dois["base"]) == Decimal("2000.00") and "estimada" in dois["origem"]  # sem rubricas classificadas
    t = r["totais"]
    assert Decimal(t["bruto"]) == Decimal("3200") and Decimal(t["base"]) == Decimal("3000") and t["dependentes"] == 1
    assert t["nome"].startswith("2 segurado(s) em 2 órgão(s)")

    res = c.get("/api/v1/reports/dipr-resumo/?competencia=2019-03&categoria=ATIVO").json()
    assert {x["orgao"]: x["segurados"] for x in res["linhas"]} == {"CAM": 1, "PREF": 1}
    assert res["totais"]["segurados"] == 2 and Decimal(res["totais"]["contribuicao"]) == Decimal("330")
    assert c.get("/api/v1/reports/dipr-analitico/export/?formato=xlsx&competencia=2019-03").status_code == 200
