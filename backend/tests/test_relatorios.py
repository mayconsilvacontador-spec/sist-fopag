"""Relatórios: catálogo por permissão, execução de todos sem erro e exportação (Excel/CSV) só com permissão."""
import pytest

from apps.reports.registry import REPORTS


def test_todos_os_relatorios_rodam(institution, master, client_for):
    c = client_for(master)
    lista = c.get("/api/v1/reports/?modulo=relatorios.folha").json()
    assert {r["codigo"] for r in lista} >= {"resumo-folhas", "rubricas", "liquidos", "retencoes"}
    for code in REPORTS:
        r = c.get(f"/api/v1/reports/{code}/")
        if r.status_code == 409 and r.json().get("code") == "regra_negocio":
            continue  # falta dado de base (folha, salário mínimo, campanha): o relatório orienta o cadastro
        assert r.status_code == 200, (code, r.json())
        body = r.json()
        assert body["colunas"] and isinstance(body["linhas"], list)


def test_exportacao_exige_permissao(institution, master, consulta, client_for):
    m = client_for(master)
    xlsx = m.get("/api/v1/reports/servidores-ativos/export/?formato=xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    csv = m.get("/api/v1/reports/servidores-ativos/export/?formato=csv")
    assert csv.status_code == 200 and csv.content.decode("utf-8").lstrip("﻿").startswith("Matrícula;Nome")
    # Consulta vê, mas não exporta
    cc = client_for(consulta)
    assert cc.get("/api/v1/reports/servidores-ativos/").status_code == 200
    assert cc.get("/api/v1/reports/servidores-ativos/export/?formato=xlsx").status_code == 403


@pytest.mark.parametrize("code", ["inexistente"])
def test_relatorio_inexistente(institution, master, client_for, code):
    assert client_for(master).get(f"/api/v1/reports/{code}/").status_code == 404
