"""
Processo DIGITALIZADO de aposentadoria já concedida → Pasta do Servidor → benefício na folha (sem redigitar):
juntar leituras, documento sem CPF, escolher pessoa, aplicar (todos os PDFs na pasta certa), implantar com
"pago pelo sistema anterior até" (sem retroativo indevido), concessão pronta para FATIMA e COMPREV.
Leitura fictícia (monkeypatch em reader.read_pdf), como em test_leitura_inteligente.
"""
from datetime import date
from decimal import Decimal

from apps.cadastros.models import Ente, Organ
from apps.concessao import fatima
from apps.concessao.models import Benefit, Concession
from apps.employment.models import EmploymentLink
from apps.folha.models import PayrollEntry
from apps.people.models import Document
from apps.protocolo.models import ProcessType, Sector

from .conftest import PASSWORD
from .test_fase5 import folha  # noqa: F401
from .test_leitura_inteligente import CPF, FICTICIO, _pdf, campo, doc, ia  # noqa: F401

URL = "/api/v1/leitura"
FICTICIO.update({
    "04 - Portaria.pdf": {"documentos": [doc("ATO", [
        campo("pessoa.nome", "SERVIDORA FICTÍCIA DE TESTE"), campo("ato.numero", "PORTARIA 123/2018"),
        campo("ato.data", "2018-05-02"), campo("ato.tipo_beneficio", "Aposentadoria voluntária por tempo de contribuição"),
        campo("ato.fundamentacao", "Art. 3º da EC 47/2005"), campo("ato.integralidade", "Sim"),
        campo("ato.paridade", "Sim"), campo("ato.valor_proventos", "4200.00"), campo("publicacao.data", "2018-05-10"),
        campo("publicacao.veiculo", "Boletim Oficial fictício nº 10")])]},
    "05 - Contracheque inativo.pdf": {"documentos": [doc("CONTRACHEQUE", [
        campo("pessoa.cpf", CPF), campo("contracheque.situacao", "Inativo"), campo("contracheque.competencia", "08/2026"),
        campo("contracheque.total_proventos", "5000.00"), campo("contracheque.total_descontos", "0.00")])]},
    "06 - Declaracao.pdf": {"documentos": [doc("DECLARACAO_ACUMULACAO", [
        campo("pessoa.nome", "SERVIDORA FICTÍCIA DE TESTE"), campo("declaracao.acumula", "Não acumulo cargo")])]},
})


def _ler(c, jid):
    for _ in range(10):
        if c.post(f"{URL}/leituras/{jid}/ler/").json()["situacao"] != "LENDO":
            break


def test_processo_digitalizado_ate_a_folha(institution, master, consulta, client_for, ia, folha):  # noqa: F811
    c = client_for(master)
    c.post(f"{URL}/configuracao/", {"api_key": "sk-ant-api03-" + "x" * 40, "privacy_ack": True, "enabled": True,
                                    "engine": "ANTHROPIC"}, format="json")
    sector = Sector.objects.create(institution=institution, name="Benefícios", code="BEN")
    sector.members.add(master)
    ProcessType.objects.create(institution=institution, name="Aposentadoria", deadline_days=60)
    organ = Organ.objects.create(institution=institution, ente=Ente.objects.create(institution=institution, name="E"),
                                 name="Prefeitura (fictícia)")

    # cada PDF lido numa leitura separada (como acontece na prática)
    jobs = {}
    for nome in ("01 - RG.pdf", "02 - CTC INSS.pdf", "03 - Contracheque.pdf", "04 - Portaria.pdf", "06 - Declaracao.pdf"):
        jid = c.post(f"{URL}/leituras/", {"titulo": nome, "arquivos": [_pdf(nome)]}, format="multipart").json()["id"]
        _ler(c, jid)
        jobs[nome] = jid
    decl = c.get(f"{URL}/leituras/{jobs['06 - Declaracao.pdf']}/").json()
    assert any("Nenhum CPF" in ch["titulo"] for ch in decl["conferencias"])
    c.post(f"{URL}/leituras/{jobs['06 - Declaracao.pdf']}/confirmar-alta/")
    r = c.post(f"{URL}/leituras/{jobs['06 - Declaracao.pdf']}/aplicar/", {}, format="json")
    assert r.status_code == 409 and "escolha a pessoa" in r.json()["detail"]

    # juntar tudo na leitura do RG e acrescentar o contracheque de inativo
    alvo = jobs["01 - RG.pdf"]
    assert client_for(consulta).post(f"{URL}/leituras/{alvo}/juntar/", {"leituras": []}, format="json").status_code == 403
    r = c.post(f"{URL}/leituras/{alvo}/juntar/", {"leituras": [v for k, v in jobs.items() if v != alvo]}, format="json")
    assert r.status_code == 200, r.json()
    assert c.get(f"{URL}/leituras/{jobs['04 - Portaria.pdf']}/").json()["status"] == "DESCARTADO"
    r = c.post(f"{URL}/leituras/{alvo}/arquivos/", {"arquivos": [_pdf("05 - Contracheque inativo.pdf")]}, format="multipart")
    assert r.status_code == 200 and r.json()["status"] == "LENDO"
    _ler(c, alvo)
    job = c.get(f"{URL}/leituras/{alvo}/").json()
    assert len(job["arquivos"]) == 6 and job["status"] == "CONFERENCIA"
    titulos = " | ".join(ch["titulo"] for ch in job["conferencias"])
    assert "CPF igual em 4 documento(s)" in titulos and "Nenhum CPF" not in titulos
    c.post(f"{URL}/leituras/{alvo}/confirmar-alta/")
    for a in c.get(f"{URL}/leituras/{alvo}/").json()["arquivos"]:  # o que não tem confiança alta a equipe confirma
        for d in a["documentos"]:
            for cp in d["campos"]:
                if not cp["confirmado"] and not cp["ignorado"]:
                    c.post(f"{URL}/leituras/{alvo}/campo/", {"campo": cp["id"], "confirmar": True}, format="json")
    r = c.post(f"{URL}/leituras/{alvo}/aplicar/", {"orgao": str(organ.pk), "massa": "PREVIDENCIARIO", "sexo": "F"},
               format="json")
    assert r.status_code == 200, r.json()
    docs = {d.doc_type for d in Document.objects.filter(person__cpf=CPF)}
    assert {"IDENTIDADE", "CTC", "CONTRACHEQUE", "ATO", "DECL_ACUMUL"} <= docs  # todo PDF na pasta certa

    # sugestões do formulário de implantação
    pre = c.get(f"{URL}/leituras/{alvo}/implantacao/").json()["sugestao"]
    assert pre["valor"] == "5000.00" and "inativo 08/2026" in pre["valor_origem"]  # contracheque, não a portaria
    assert pre["modalidade"] == 2 and pre["ato_numero"] == "PORTARIA 123/2018" and pre["inicio"] == "2018-05-10"
    assert pre["integralidade"] is True and pre["paridade"] is True

    body = {"tipo": "APOSENTADORIA", "vinculo": pre["vinculo"], "modalidade": 2, "fundamentacao": pre["fundamentacao"],
            "ato_numero": pre["ato_numero"], "ato_data": pre["ato_data"], "publicacao_data": pre["publicacao_data"],
            "publicacao_veiculo": pre["publicacao_veiculo"], "inicio": pre["inicio"], "valor": "5000,00",
            "integralidade": True, "paridade": True, "folha": pre["folha"], "pago_ate": "2026-08",
            "processo_original": "158/2018", "tce": "LEGAL", "tce_processo": "TCE 999/2019", "tce_julgamento": "2019-11-20"}
    assert client_for(consulta).post(f"{URL}/leituras/{alvo}/implantar/", {**body, "password": PASSWORD}, format="json").status_code == 403
    assert c.post(f"{URL}/leituras/{alvo}/implantar/", {**body, "password": "errada"}, format="json").status_code in (400, 409)
    r = c.post(f"{URL}/leituras/{alvo}/implantar/", {**body, "password": PASSWORD}, format="json")
    assert r.status_code == 201, r.json()
    res = r.json()
    con = Concession.objects.get(pk=res["concessao"])
    assert con.stage == "IMPLANTADO" and con.process.external_number == "158/2018" and con.tce_result == "LEGAL"
    assert con.process.status == "CONCLUIDO" and con.steps.filter(action="IMPLANTACAO").exists()
    b = Benefit.objects.get(pk=res["beneficio"])
    assert b.amount == Decimal("5000.00") and b.paid_until == date(2026, 8, 1) and b.payroll_group.code == "PREV"
    link = EmploymentLink.objects.get(pk=pre["vinculo"])
    assert link.status == "APOSENTADO" and link.end_date == date(2018, 5, 9)
    assert res["comprev_averbacoes"] == 0 or res["comprev_averbacoes"] >= 0
    assert fatima.ficha(con)["passos"]["1_informacoes_iniciais"]["aposentadoria"]["Nº do ato concessório"] == "PORTARIA 123/2018"
    # não implanta duas vezes
    assert c.post(f"{URL}/leituras/{alvo}/implantar/", {**body, "password": PASSWORD}, format="json").status_code == 409

    # folha de 09/2026: paga o mês, SEM retroativo de 2018 a 08/2026
    run = c.post("/api/v1/folha/folhas/", {"payroll_group": str(b.payroll_group_id), "year": 2026, "month": 9,
                                          "kind": "MENSAL"}, format="json")
    assert run.status_code == 201, run.json()
    c.post(f"/api/v1/folha/folhas/{run.json()['id']}/calculate/")
    e = PayrollEntry.objects.get(benefit=b)
    assert e.gross == Decimal("5000.00") and "retroativo" not in e.memory
