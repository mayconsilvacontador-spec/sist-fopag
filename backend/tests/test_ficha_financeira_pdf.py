"""Ficha financeira ANUAL em PDF (texto digital): leitura por coluna e conferência com os totais do relatório.
O PDF é FICTÍCIO, montado aqui no mesmo leiaute do relatório "Ficha Financeira Anual" (uma página por ano)."""
from datetime import date
from decimal import Decimal

import pymupdf
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cadastros.models import Ente, Organ, Position
from apps.employment.models import EmploymentLink
from apps.pessoal.models import FinancialLine

from .test_fase5 import cpf, person

URL = "/api/v1/ativos/ficha-financeira"
COLS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez", "13º Salário", "Total"]
RIGHT = [205, 254, 302, 350, 398, 445, 492, 542, 595, 644, 692, 746, 803, 846]


def _fmt(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pdf(cpf_fmt, year, prov, desc, total_errado=False):
    doc = pymupdf.open()
    pg = doc.new_page(width=862, height=616)
    t = lambda x, y, s: pg.insert_text((x, y), s, fontsize=7)  # noqa: E731
    t(40, 40, "PREFEITURA MUNICIPAL FICTICIA")
    t(780, 40, f"ANO DE {year}")
    t(37, 80, "Servidor:")
    t(110, 80, "9001.1 - SERVIDOR FICTICIO")
    t(560, 110, "CPF:")
    t(580, 110, cpf_fmt)
    y = 190

    def bloco(titulo, linhas, total_label):
        nonlocal y
        t(37, y, titulo)
        for c, r in zip(COLS, RIGHT):
            t(r - pymupdf.get_text_length(c, fontsize=7), y, c)
        y += 11
        tot = [Decimal(0)] * 14
        for code, name, vals in linhas:
            t(37, y, code)
            t(63, y, name)
            full = vals + [sum(vals, Decimal(0))]
            for i, v in enumerate(full):
                s = _fmt(v)
                t(RIGHT[i] + 12 - pymupdf.get_text_length(s, fontsize=7), y, s)
                tot[i] += v
            y += 11
        t(37, y, total_label)
        if total_errado:
            tot[0] += 1
        for i, v in enumerate(tot):
            s = _fmt(v)
            t(RIGHT[i] + 12 - pymupdf.get_text_length(s, fontsize=7), y, s)
        y += 30
        return tot

    tp = bloco("PROVENTOS", prov, "TOTAL PROVENTOS")
    td = bloco("DESCONTOS", desc, "TOTAL DESCONTOS")
    t(40, y, "LÍQUIDOS")
    for i in range(14):
        s = _fmt(tp[i] - td[i])
        t(RIGHT[i] + 12 - pymupdf.get_text_length(s, fontsize=7), y, s)
    return doc.tobytes()


def _m(*pairs, decimo=Decimal(0)):
    v = [Decimal(0)] * 12
    for mes, val in pairs:
        v[mes - 1] = Decimal(val.replace(",", "."))
    return v + [decimo]


def test_importa_ficha_anual_em_pdf(institution, master, client_for):
    organ = Organ.objects.create(institution=institution, ente=Ente.objects.create(institution=institution, name="M"),
                                 name="Prefeitura")
    p = person(institution, 600000011, "Servidor Ficticio", date(1980, 1, 1))
    EmploymentLink.objects.create(institution=institution, person=p, organ=organ,
                                  position=Position.objects.create(institution=institution, name="AUX"),
                                  registration="9001.1", public_service_start=date(2011, 1, 1),
                                  ente_start=date(2011, 1, 1), position_start=date(2011, 1, 1))
    c_ = cpf(600000011)
    cpf_fmt = f"{c_[:3]}.{c_[3:6]}.{c_[6:9]}-{c_[9:]}"
    prov = [("1", "VENCIMENTO", _m((8, "1272,50"), (9, "2545,00"), (12, "2545,00"))),
            ("200", "13 SALARIO (MESES)", _m(decimo=Decimal("1060.42")))]
    desc = [("3", "DESCONTO PREVIDENCIA", _m((8, "139,98"), (9, "279,95"), (12, "279,95")))]
    content = _pdf(cpf_fmt, 2012, prov, desc)
    c = client_for(master)
    up = lambda b: SimpleUploadedFile("ficha.pdf", b, content_type="application/pdf")  # noqa: E731
    r = c.post(f"{URL}/importar/", {"file": up(content)}, format="multipart").json()
    assert r["gravado"] is False and r["pdf"]["anos"] == [2012] and r["avisos"] == [], r
    assert r["incluidas"] == 7 and r["total_erros"] == 0 and r["periodo"] == ["08/2012", "12/2012"]
    assert not r["sem_classificacao_rpps"]  # DESCONTO PREVIDENCIA reconhecido
    r = c.post(f"{URL}/importar/", {"file": up(content), "confirmar": "1"}, format="multipart").json()
    assert r["gravado"]
    lines = FinancialLine.objects.filter(person=p)
    assert lines.count() == 7 and lines.get(code="200").payroll_kind == "DECIMO"
    assert lines.get(code="1", competence=date(2012, 9, 1)).amount == Decimal("2545.00")
    assert lines.get(code="3", competence=date(2012, 8, 1)).category == "CONTRIB_RPPS"
    assert lines.filter(link__registration="9001.1").count() == 7

    # total do relatório que não bate vira aviso (nada é ajustado)
    r = c.post(f"{URL}/importar/", {"file": up(_pdf(cpf_fmt, 2013, prov, desc, total_errado=True))},
               format="multipart").json()
    assert any("TOTAL PROVENTOS" in a for a in r["avisos"])
    # PDF de outro tipo é recusado com explicação
    outro = pymupdf.open()
    outro.new_page().insert_text((50, 50), "Relatorio qualquer sem a ficha financeira anual " * 3)
    assert c.post(f"{URL}/importar/", {"file": up(outro.tobytes())}, format="multipart").status_code == 409
