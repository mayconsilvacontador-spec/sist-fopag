"""Importação complementar (leiaute SIST) no mesmo lote do SPREV: complemento, endereço, conta, averbação e histórico."""
from datetime import date

from apps.employment.models import FunctionalEvent
from apps.people.importers.sprev import SprevImporter
from apps.people.models import Address, BankAccount, ImportBatch, Person
from apps.previdencia.models import Averbacao

CPF = "52998224725"


def _run(inst, tables, apply=True):
    b = ImportBatch.objects.create(institution=inst, source_system="teste")
    return SprevImporter(inst, b, "teste").run(tables, apply=apply)


SERV = [{"NO_ENTE": "Município Fictício", "SG_UF": "RJ", "CO_TIPO_FUNDO": "1", "NO_ORGAO": "PREFEITURA FICTÍCIA",
         "ID_SERVIDOR_MATRICULA": "777", "ID_SERVIDOR_CPF": "529.982.247-25", "CO_SEXO_SERVIDOR": "1",
         "DT_NASC_SERVIDOR": "10/03/1968", "DT_ING_SERV_PUB": "01/03/2000", "NO_CARGO": "PROFESSOR II",
         "CO_TIPO_CARGO": "2", "NO_SERVIDOR": "SERVIDORA FICTÍCIA"}]


def test_lote_spREV_mais_complementares(institution):
    from apps.institutions.services import ensure_payroll_groups

    ensure_payroll_groups(institution)
    tables = [
        ("SERVIDORES.csv", SERV),
        ("PESSOAS_COMPLEMENTO.csv", [{"CPF": CPF, "NOME_MAE": "Mãe Fictícia", "RG": "123456", "RG_ORGAO": "detran",
                                      "RG_UF": "RJ", "RG_DATA": "05/05/1990", "RACA_COR": "3", "EMAIL": "x@exemplo.invalid"}]),
        ("ENDERECOS.csv", [{"CPF": CPF, "LOGRADOURO": "RUA A", "NUMERO": "10", "CIDADE": "Cidade", "UF": "RJ",
                            "CEP": "27980000", "INICIO": "01/01/2010"},
                           {"CPF": CPF, "LOGRADOURO": "RUA B", "NUMERO": "20", "CIDADE": "Cidade", "UF": "RJ",
                            "INICIO": "01/01/2020"}]),
        ("CONTAS_BANCARIAS.csv", [{"CPF": CPF, "BANCO": "1", "NOME_BANCO": "BANCO DO BRASIL", "AGENCIA": "1234",
                                   "CONTA": "56789", "TIPO_CONTA": "CORRENTE", "INICIO": "01/01/2015"}]),
        ("AVERBACOES_CTC.csv", [{"CPF": CPF, "NATUREZA_TEMPO": "1", "ORGAO_EMISSOR": "INSS", "NUMERO_CTC": "10/2001",
                                 "INICIO": "01/01/1990", "FIM": "31/12/1999", "DIAS_LIQUIDOS": "3600",
                                 "MAGISTERIO": "S", "COMPREV": "S"},
                                {"CPF": CPF, "NATUREZA_TEMPO": "03", "ORGAO_EMISSOR": "OUTRO RPPS", "INICIO": "01/01/1985",
                                 "FIM": "31/12/1985", "DIAS_LIQUIDOS": "999"}]),  # mais dias que o período: erro
        ("HISTORICO_FUNCIONAL.csv", [{"CPF": CPF, "MATRICULA": "777", "TIPO_EVENTO": "FALTAS", "INICIO": "01/03/2005",
                                      "FIM": "31/03/2005", "DIAS": "3"},
                                     {"CPF": CPF, "MATRICULA": "777", "TIPO_EVENTO": "PROGRESSAO",
                                      "INICIO": "01/03/2008", "NUMERO_ATO": "12/2008"},
                                     {"CPF": CPF, "MATRICULA": "999", "TIPO_EVENTO": "FALTAS", "INICIO": "01/03/2005",
                                      "DIAS": "1"}]),  # matrícula inexistente: erro
    ]
    rep = _run(institution, tables, apply=False)  # validação não grava nada
    assert not Person.objects.filter(cpf=CPF).exists()
    tipos = {a["nome"]: a["tipo"] for a in rep["arquivos"]}
    assert tipos["AVERBACOES_CTC.csv"] == "Averbações (CTC)" and tipos["HISTORICO_FUNCIONAL.csv"] == "Histórico funcional"
    assert rep["total_erros"] == 2

    rep = _run(institution, tables)
    assert rep["resumo"]["averbacoes"] == 1 and rep["resumo"]["eventos_funcionais"] == 2
    p = Person.objects.get(cpf=CPF)
    assert p.mother_name == "MÃE FICTÍCIA" and p.rg_issuer == "DETRAN" and p.race == 3
    ends = list(Address.objects.filter(person=p).order_by("valid_from"))
    assert len(ends) == 2 and ends[0].valid_to == date(2019, 12, 31) and ends[1].valid_to is None  # vigência
    assert BankAccount.objects.get(person=p).bank.code == "001"
    av = Averbacao.objects.get(person=p)
    assert av.nature == "01" and av.magisterio and av.comprev and av.certified_days == 3600
    falta = FunctionalEvent.objects.get(link__person=p, event_type="FALTAS")
    assert falta.days == 3 and not falta.counts_as_service
    # reimportar o mesmo lote não duplica nada
    rep = _run(institution, tables)
    assert Averbacao.objects.filter(person=p).count() == 1 and FunctionalEvent.objects.filter(link__person=p).count() == 2
    assert Address.objects.filter(person=p).count() == 2
