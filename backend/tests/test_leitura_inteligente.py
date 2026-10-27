"""
Leitura inteligente: configuração (chave criptografada), fila de leitura, conferências automáticas entre documentos,
conferência pela equipe e aplicação ao Cadastro Único. A chamada à API é SUBSTITUÍDA no teste por uma leitura
fictícia (monkeypatch em reader.read_pdf) — nenhum dado sai do computador.
"""
import pytest
from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cadastros.models import Ente, Organ
from apps.employment.models import EmploymentLink, FunctionalEvent
from apps.leitura import reader
from apps.leitura.models import AiSettings
from apps.people.models import Document, Person
from apps.previdencia.models import Averbacao

URL = "/api/v1/leitura"
CPF = "52998224725"  # CPF fictício válido


def campo(chave, valor, pagina=1, confianca="alta"):
    return {"chave": chave, "rotulo": "", "valor": valor, "pagina": pagina, "trecho": valor, "confianca": confianca}


def doc(tipo, campos, freq=None, rub=None, p1=1, p2=1):
    return {"tipo": tipo, "titulo": tipo, "pagina_inicial": p1, "pagina_final": p2, "legibilidade": "boa",
            "observacoes": "", "campos": campos, "frequencia": freq or [], "rubricas": rub or []}


def linha(periodo, bruto, faltas, liquido):
    return {"periodo": periodo, "bruto": bruto, "faltas": faltas, "licencas": 0, "suspensoes": 0, "outras": 0,
            "liquido": liquido, "pagina": 1}


FICTICIO = {
    "01 - RG.pdf": {"documentos": [doc("RG_CPF", [
        campo("pessoa.nome", "SERVIDORA FICTÍCIA DE TESTE"), campo("pessoa.cpf", CPF),
        campo("pessoa.data_nascimento", "1968-03-10"), campo("pessoa.nome_mae", "MÃE FICTÍCIA"),
        campo("pessoa.rg_numero", "123456789", confianca="media")])]},
    "02 - CTC INSS.pdf": {"documentos": [doc("CTC", [
        campo("pessoa.nome", "SERVIDORA FICTICIA DE TESTE"), campo("pessoa.cpf", CPF),
        campo("ctc.numero", "CTC-FICT-77"), campo("ctc.orgao_emissor", "INSS (fictício)"),
        campo("ctc.regime_origem", "RGPS"), campo("ctc.periodo_inicio", "1990-01-01"),
        campo("ctc.periodo_fim", "1991-12-31"), campo("ctc.total_liquido_dias", "725")],
        freq=[linha("1990", 365, 3, 362), linha("1991", 365, 2, 363)])]},
    "03 - Contracheque.pdf": {"documentos": [doc("CONTRACHEQUE", [
        campo("pessoa.cpf", CPF), campo("vinculo.matricula", "4321"), campo("vinculo.cargo", "PROFESSOR II"),
        campo("vinculo.data_admissao", "2000-03-01"), campo("contracheque.total_proventos", "6258.41"),
        campo("contracheque.total_descontos", "892.80")],
        rub=[{"codigo": "1001", "descricao": "VENCIMENTO", "referencia": "30", "valor": "4470.29",
              "natureza": "provento", "pagina": 1},
             {"codigo": "1018", "descricao": "TRIÊNIO", "referencia": "40", "valor": "1788.12",
              "natureza": "provento", "pagina": 1},
             {"codigo": "1058", "descricao": "IRRF", "referencia": "", "valor": "892.80", "natureza": "desconto",
              "pagina": 1}])]},
}


@pytest.fixture
def ia(settings, monkeypatch):
    settings.SIST_SECRETS_KEY = Fernet.generate_key().decode()
    calls = []

    def fake_read(api_key, model, data, file_name):
        calls.append((api_key, model, file_name))
        return FICTICIO[file_name], 12000, 3000

    def fake_test(api_key, model):
        from apps.core.exceptions import BusinessRuleError

        if "recusada" in api_key:
            raise BusinessRuleError("Chave de API inválida ou revogada.")
        return f"Conexão OK com {model}."

    monkeypatch.setattr(reader, "read_pdf", fake_read)
    monkeypatch.setattr(reader, "test_key", fake_test)
    return calls


def _pdf(name):
    return SimpleUploadedFile(name, b"%PDF-1.4 documento ficticio " + name.encode(), content_type="application/pdf")


def test_leitura_conferencia_e_aplicacao(institution, master, consulta, client_for, ia):
    c = client_for(master)
    # Configuração: chave guardada criptografada; ativar exige ciência sobre dados pessoais
    assert client_for(consulta).post(f"{URL}/configuracao/", {"api_key": "sk-ant-x"}, format="json").status_code == 403
    assert c.post(f"{URL}/configuracao/", {"api_key": "chave-errada"}, format="json").status_code == 409  # curta
    r = c.post(f"{URL}/configuracao/", {"api_key": "sk-ant-admin01-" + "z" * 30}, format="json")
    assert r.status_code == 409 and "ADMINISTRAÇÃO" in r.json()["detail"]
    r = c.post(f"{URL}/configuracao/", {"api_key": "chave-recusada-" + "z" * 30}, format="json")
    assert r.status_code == 409 and "recusou" in r.json()["detail"]
    assert not AiSettings.objects.filter(institution=institution).exclude(key_hint="").exists()  # recusada: não guarda
    chave = "sk-ant-api03-" + "x" * 40
    # espaços/quebras de linha copiados junto são removidos; outro formato de chave é aceito se a Anthropic aceitar
    r = c.post(f"{URL}/configuracao/", {"api_key": "  outro-formato-" + "w" * 30 + "\n"}, format="json")
    assert r.status_code == 200 and r.json()["chave_final"] == "wwww" and "Conexão OK" in r.json()["resultado_teste"]
    r = c.post(f"{URL}/configuracao/", {"api_key": chave, "enabled": True}, format="json")
    assert r.status_code == 409  # falta a ciência de privacidade
    r = c.post(f"{URL}/configuracao/", {"api_key": chave, "privacy_ack": True, "enabled": True, "engine": "ANTHROPIC",
                                        "model": "claude-sonnet-5-5"}, format="json")
    assert r.status_code == 200 and r.json()["ativo"] and r.json()["chave_final"] == chave[-4:]
    assert chave.encode() not in bytes(AiSettings.objects.get(institution=institution).api_key)

    r = c.post(f"{URL}/leituras/", {"titulo": "Processo fictício", "arquivos": [
        _pdf("01 - RG.pdf"), _pdf("02 - CTC INSS.pdf"), _pdf("03 - Contracheque.pdf")]}, format="multipart")
    assert r.status_code == 201, r.json()
    jid = r.json()["id"]
    for _ in range(3):
        prog = c.post(f"{URL}/leituras/{jid}/ler/").json()
    assert prog["lidos"] == 3 and prog["situacao"] == "CONFERENCIA" and prog["custo_estimado_usd"] > 0
    assert ia[0][0] == chave and ia[0][1] == "claude-sonnet-5-5"  # a chave decifrada vai só para a chamada

    job = c.get(f"{URL}/leituras/{jid}/").json()
    titulos = " | ".join(ch["titulo"] for ch in job["conferencias"])
    assert "CPF igual em 3 documento(s)" in titulos
    assert "CTC conferida" in titulos and "total de proventos confere" in titulos
    assert "Nome diferente" not in titulos  # acento não conta como divergência
    assert any(ch["nivel"] == "aviso" and "não conferido" in ch["titulo"] for ch in job["conferencias"])

    # Aplicar sem conferir tudo é recusado
    assert c.post(f"{URL}/leituras/{jid}/aplicar/", {}, format="json").status_code == 409
    assert c.post(f"{URL}/leituras/{jid}/confirmar-alta/").json()["confirmados"] > 0
    rg = next(cp for a in job["arquivos"] for d in a["documentos"] for cp in d["campos"]
              if cp["chave"] == "pessoa.rg_numero")
    r = c.post(f"{URL}/leituras/{jid}/campo/", {"campo": rg["id"], "valor": "987654321"}, format="json")
    assert r.status_code == 200 and r.json()["confirmado"] and r.json()["original"] == "123456789"

    organ = Organ.objects.create(institution=institution, ente=Ente.objects.create(institution=institution, name="E"),
                                 name="Prefeitura (fictícia)")
    ctc_id = next(d["id"] for a in job["arquivos"] for d in a["documentos"] if d["tipo"] == "CTC")
    r = c.post(f"{URL}/leituras/{jid}/aplicar/", {"orgao": str(organ.pk), "massa": "FINANCEIRO", "sexo": "F",
                                                   "ctc": {ctc_id: "AVERBACAO"}}, format="json")
    assert r.status_code == 200, r.json()
    p = Person.objects.get(institution=institution, cpf=CPF)
    assert p.name == "SERVIDORA FICTÍCIA DE TESTE" and p.rg_number == "987654321" and p.sex == 1
    link = EmploymentLink.objects.get(person=p)
    assert link.registration == "4321" and link.position.name == "PROFESSOR II" and link.segment == "FINANCEIRO"
    av = Averbacao.objects.get(person=p)
    assert av.nature == "01" and av.certified_days == 725 and av.certificate_number == "CTC-FICT-77"
    assert Document.objects.filter(person=p).count() == 3
    assert c.get(f"{URL}/leituras/{jid}/").json()["status"] == "APLICADO"
    assert c.post(f"{URL}/leituras/{jid}/descartar/").status_code == 409


def test_divergencias_bloqueiam_aplicacao(institution, master, client_for, ia):
    c = client_for(master)
    c.post(f"{URL}/configuracao/", {"api_key": "sk-ant-api03-" + "y" * 40, "privacy_ack": True, "enabled": True,
                                    "engine": "ANTHROPIC"},
           format="json")
    errado = {"documentos": [doc("CTC", [campo("pessoa.cpf", CPF), campo("ctc.total_liquido_dias", "999")],
                                 freq=[linha("2001", 365, 5, 362)])]}
    FICTICIO["99 - CTC errada.pdf"] = errado
    try:
        jid = c.post(f"{URL}/leituras/", {"arquivos": [_pdf("99 - CTC errada.pdf")]}, format="multipart").json()["id"]
        c.post(f"{URL}/leituras/{jid}/ler/")
        checks = c.get(f"{URL}/leituras/{jid}/").json()["conferencias"]
        erros = [ch["titulo"] for ch in checks if ch["nivel"] == "erro"]
        assert any("conta errada em 2001" in e for e in erros) and any("soma dos anos" in e for e in erros)
        c.post(f"{URL}/leituras/{jid}/confirmar-alta/")
        r = c.post(f"{URL}/leituras/{jid}/aplicar/", {"sexo": "F"}, format="json")
        assert r.status_code == 409 and "divergências" in r.json()["detail"]
        assert not FunctionalEvent.objects.exists()
    finally:
        FICTICIO.pop("99 - CTC errada.pdf")


def test_ia_exige_ativacao(institution, master, client_for, ia):
    r = client_for(master).post(f"{URL}/configuracao/", {"engine": "ANTHROPIC"}, format="json")
    assert r.status_code == 409 and "leitura local" in r.json()["detail"]


# ------------------------------------------------------------------ leitura local (OCR), sem custo e sem internet
def _pdf_local(pages: list[list[str]], scanned_page: list[str] | None = None) -> bytes:
    """PDF fictício: páginas com texto (PDF digital) e, opcionalmente, uma página só com IMAGEM (digitalizada)."""
    import pymupdf

    doc = pymupdf.open()
    for lines in pages:
        pg = doc.new_page(width=595, height=842)
        for i, ln in enumerate(lines):
            pg.insert_text((50, 60 + i * 22), ln, fontsize=11)
    if scanned_page:
        src = pymupdf.open()
        sp = src.new_page(width=595, height=842)
        for i, ln in enumerate(scanned_page):
            sp.insert_text((50, 80 + i * 30), ln, fontsize=16)
        png = sp.get_pixmap(dpi=200).tobytes("png")
        img = doc.new_page(width=595, height=842)
        img.insert_image(img.rect, stream=png)
    return doc.tobytes()


def test_leitura_local_sem_custo(institution, master, client_for, settings):
    c = client_for(master)
    assert c.get(f"{URL}/configuracao/").json()["motor"] == "LOCAL"  # padrão: gratuito, já pronto
    hist = _pdf_local([[
        "PREFEITURA MUNICIPAL FICTICIA", "HISTORICO FUNCIONAL",
        "Nome: SERVIDORA FICTICIA DE TESTE", "Matricula: 4321", "Data Admissao: 01/03/2000",
        "Cargo: PROFESSOR II", "Data de Nascimento: 10/03/1968", "CPF: 529.982.247-25",
        "Carteira de Identidade: 12345678", "PIS/PASEP: 12056412545"]])
    import pymupdf

    cdoc = pymupdf.open()
    cp = cdoc.new_page(width=595, height=842)
    cp.insert_text((50, 60), "CERTIDAO DE TEMPO DE CONTRIBUICAO N.o 077/2026", fontsize=11)
    xs = [50, 120, 180, 240, 310, 390, 450, 510]  # colunas alinhadas como na certidão impressa
    for y, cells in ((100, ["ANO", "BRUTO", "FALTAS", "LICENCAS", "SUSPENSOES", "OUTRAS", "SOMA", "LIQUIDO"]),
                     (125, ["2001", "365", "2", "-", "-", "-", "2", "363"]),
                     (150, ["2002", "365", "-", "-", "-", "-", "-", "365"])):
        for x, cell in zip(xs, cells):
            cp.insert_text((x, y), cell, fontsize=9)
    cp.insert_text((50, 190), "TEMPO LIQUIDO APURADO NO ORGAO: 728", fontsize=11)
    ctc = cdoc.tobytes()
    rg = _pdf_local([], scanned_page=["REPUBLICA FEDERATIVA DO BRASIL", "CARTEIRA DE IDENTIDADE",
                                      "NOME: SERVIDORA FICTICIA DE TESTE", "CPF: 529.982.247-25"])
    files = [SimpleUploadedFile(n, b, content_type="application/pdf") for n, b in
             (("14 - Historico Funcional.pdf", hist), ("04 - Certidao de Tempo de Contribuicao.pdf", ctc),
              ("06 - RG e CPF.pdf", rg))]
    r = c.post(f"{URL}/leituras/", {"titulo": "Processo fictício (OCR)", "arquivos": files}, format="multipart")
    assert r.status_code == 201, r.json()
    jid = r.json()["id"]
    assert r.json()["engine"] == "LOCAL"
    for _ in range(10):
        prog = c.post(f"{URL}/leituras/{jid}/ler/").json()
        if prog["situacao"] != "LENDO":
            break
    assert prog["situacao"] == "CONFERENCIA" and prog["custo_estimado_usd"] == 0 and prog["paginas_lidas"] == 3

    job = c.get(f"{URL}/leituras/{jid}/").json()
    docs = {d["tipo"]: d for a in job["arquivos"] for d in a["documentos"]}
    assert {"HISTORICO_FUNCIONAL", "CTC", "RG_CPF"} <= set(docs)
    val = {c_["chave"]: c_["valor"] for c_ in docs["HISTORICO_FUNCIONAL"]["campos"]}
    assert val["pessoa.cpf"] == CPF and val["pessoa.data_nascimento"] == "1968-03-10"
    assert val["vinculo.matricula"] == "4321" and val["vinculo.data_admissao"] == "2000-03-01"
    assert val["pessoa.pis_pasep"] == "12056412545" and val["vinculo.cargo"] == "PROFESSOR II"
    assert all(c_.get("caixa") for c_ in docs["HISTORICO_FUNCIONAL"]["campos"])  # posição para o destaque
    freq = docs["CTC"]["frequencia"]
    assert [(r_["periodo"], r_["bruto"], r_["faltas"], r_["liquido"]) for r_ in freq] == [("2001", 365, 2, 363),
                                                                                       ("2002", 365, 0, 365)]
    assert {c_["chave"]: c_["valor"] for c_ in docs["CTC"]["campos"]}["ctc.total_liquido_dias"] == "728"
    # página digitalizada (imagem): o OCR acha o CPF pelo dígito verificador
    assert any(c_["chave"] == "pessoa.cpf" and c_["valor"] == CPF for c_ in docs["RG_CPF"]["campos"])
    titulos = " | ".join(ch["titulo"] for ch in job["conferencias"])
    assert "CTC conferida" in titulos

    # Correção de célula da tabela da CTC (o OCR erra números pequenos) refaz as conferências
    r = c.post(f"{URL}/leituras/{jid}/linha/", {"documento": docs["CTC"]["id"], "indice": 0, "coluna": "faltas",
                                                 "valor": "5"}, format="json")
    assert r.status_code == 200 and r.json()["corrigido"]
    erros = [ch["titulo"] for ch in c.get(f"{URL}/leituras/{jid}/").json()["conferencias"] if ch["nivel"] == "erro"]
    assert any("conta errada em 2001" in e for e in erros)
    # imagem da página com o dado destacado
    campo_cpf = next(c_ for c_ in docs["HISTORICO_FUNCIONAL"]["campos"] if c_["chave"] == "pessoa.cpf")
    arq = next(a["id"] for a in job["arquivos"] if a["nome"].startswith("14"))
    caixa = ",".join(str(v) for v in campo_cpf["caixa"])
    img = c.get(f"{URL}/leituras/{jid}/arquivo/{arq}/pagina/1/?caixa={caixa}")
    assert img.status_code == 200 and img["Content-Type"] == "image/png" and img.content[:4] == b"\x89PNG"


def test_ctc_leitura_duvidosa_e_ajustada_e_marcada():
    """Erros típicos do OCR na CTC: dígito trocado (264 no lugar de 364), sujeira antes do ano, líquido não lido."""
    import pymupdf

    from apps.leitura import ocr

    d = pymupdf.open()
    pg = d.new_page(width=595, height=842)
    pg.insert_text((50, 60), "CERTIDAO DE TEMPO DE CONTRIBUICAO N.o 001/2026", fontsize=11)
    xs = [50, 120, 180, 240, 310, 390, 450, 510]
    for y, cells in ((100, ["ANO", "BRUTO", "FALTAS", "LICENCAS", "SUSPENSOES", "OUTRAS", "SOMA", "LIQUIDO"]),
                     (125, ["2010", "365", "", "", "", "", "", "264"]),
                     (150, ["=.", "2024", "365"]),
                     (175, ["2018", "369", "-", "-", "-", "-", "-", "365"])):
        for x, cell in zip(xs if cells[0] != "=." else [20, 50, 120], cells):
            if cell:
                pg.insert_text((x, y), cell, fontsize=9)
    pg.insert_text((50, 215), "TEMPO LIQUIDO APURADO NO ORGAO: 1094", fontsize=11)
    lines, _ = ocr.page_lines(pg)
    out = ocr.extract("04 - CTC.pdf", [{"n": 1, "linhas": lines, "ocr": False}])
    rows = {r["periodo"]: r for r in out["documentos"][0]["frequencia"]}
    assert (rows["2010"]["liquido"], rows["2010"]["faltas"], rows["2010"].get("suspeito")) == (364, 1, True)
    assert (rows["2024"]["liquido"], rows["2024"].get("suspeito")) == (365, True)  # linha com "=." antes do ano
    assert (rows["2018"]["bruto"], rows["2018"]["faltas"], rows["2018"].get("suspeito")) == (365, 0, True)
    assert sum(r["liquido"] for r in rows.values()) == 1094
