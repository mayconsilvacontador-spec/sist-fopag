"""Tabela padrão de servidores do SIST: modelo Excel e importação (admissão completa por linha)."""
import io

import openpyxl

from apps.cadastros.models import Bank
from apps.employment.models import EmploymentLink
from apps.people.importers.sprev import SprevImporter
from apps.people.models import ImportBatch, Person

ROW = {"CPF": "529.982.247-25", "NOME": "Servidor Padrão Fictício", "DATA_NASCIMENTO": "10/02/1990", "SEXO": "M",
       "ESTADO_CIVIL": "1", "ORGAO": "Prefeitura Fictícia", "CARGO": "AGENTE ADMINISTRATIVO", "MATRICULA": "15481",
       "CLASSE_NIVEL": "15", "VENCIMENTO_BASE": "1.320,00", "CARGA_HORARIA": "40", "DATA_NOMEACAO": "01/02/2026",
       "DATA_POSSE": "10/02/2026", "PORTARIA_NOMEACAO": "022/2026", "LOGRADOURO": "Rua Fictícia", "NUMERO": "1",
       "CIDADE": "Cidade", "UF": "RJ", "BANCO": "33", "AGENCIA": "100", "CONTA": "1000002", "CONTA_DV": "4"}


def _run(inst, rows, apply=True):
    b = ImportBatch.objects.create(institution=inst, source_system="teste")
    return SprevImporter(inst, b, "teste").run([("SERVIDORES_PADRAO.csv", rows)], apply=apply)


def test_modelo_e_importacao_padrao(institution, master, client_for):
    r = client_for(master).get("/api/v1/imports/modelo-servidores/")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    header = [c.value for c in wb["SERVIDORES"][1]]
    assert header[:4] == ["CPF", "NOME", "DATA_NASCIMENTO", "SEXO"] and "DATA_NOMEACAO" in header

    Bank.objects.create(institution=institution, code="033", name="Banco Fictício")
    rep = _run(institution, [ROW], apply=False)  # validação não grava
    assert rep["total_erros"] == 0, rep["erros"]
    assert not Person.objects.filter(cpf="52998224725").exists()
    bad = dict(ROW, CPF="52998224725", MATRICULA="2", DATA_NOMEACAO="31/02/2026")
    rep = _run(institution, [ROW, bad, dict(ROW, MATRICULA="3", BANCO="999")])
    assert rep["resumo"]["vinculos"] == 1 and rep["total_erros"] == 2, rep
    link = EmploymentLink.objects.get(registration="15481")
    assert str(link.base_salary) == "1320.00" and link.weekly_hours == 40
    assert {e.event_type for e in link.events.all()} == {"NOMEACAO", "POSSE"}
    assert link.person.bank_accounts.get().account == "1000002"
    rep = _run(institution, [ROW])  # repetir não duplica
    assert rep["resumo"]["vinculos_existentes"] == 1 and EmploymentLink.objects.count() == 1
