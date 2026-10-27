"""
Leitura LOCAL e gratuita (sem internet): OCR Tesseract (português) + regras.

1. Cada página vira imagem (300 dpi, preto e branco) e o Tesseract devolve as palavras com posição e confiança.
   Páginas que já têm texto (PDF digital) são lidas direto, sem OCR.
2. As palavras viram linhas e "blocos" (colunas separadas por espaço grande), com a caixa de cada bloco na página.
3. Cada página é classificada pelo nome do arquivo e por palavras-chave (CTC, histórico funcional, contracheque...).
4. Os dados saem por rótulo ("Data de Nascimento", "Matrícula"...): o valor está na mesma linha ou logo abaixo, na
   mesma coluna. CPF e PIS são conferidos pelo dígito verificador (com correção das trocas comuns do OCR: O→0, l→1).
5. Tabela da CTC e rubricas do contracheque: cada número é posto na coluna mais próxima do cabeçalho.

O resultado tem o MESMO formato da leitura por IA (reader.SCHEMA), mais a "caixa" de cada dado para destacar na
página. A precisão é menor: a conferência da equipe e as contas automáticas (CTC, totais) apontam o que corrigir.
"""
import re
import subprocess
from collections import Counter
import tempfile
import unicodedata
from datetime import date

from apps.core.validators import is_valid_cpf

DPI = 300
THRESHOLD = 170
MONTHS = {m: i + 1 for i, m in enumerate(["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
                                          "setembro", "outubro", "novembro", "dezembro"])}
FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1", "i": "1", "/": "7",
                     "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "g": "9"})


def plain(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


# ================================================================== OCR por página
def _words_from_text_layer(page):
    out = []
    for x0, y0, x1, y1, w, *_ in page.get_text("words"):
        out.append((x0, y0, x1, y1, w, 100.0))
    return out


def _words_from_ocr(page):
    """
    Várias leituras da mesma página, em paralelo, e fica a com mais palavras confiáveis:
    - limiar fixo e limiar automático (Otsu), modo "bloco de texto" (psm 6): melhor para tabelas alinhadas;
    - modo "texto esparso" (psm 11): resiste a faixas cinzas/carimbos que fazem o psm 6 devolver quase nada
      (ex.: página 2 da CTC de Mangaratiba, onde o psm 6 perdia os anos 2016–2024).
    """
    from concurrent.futures import ThreadPoolExecutor

    import pymupdf

    pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    otsu = _otsu(pix.samples)
    variants = [(THRESHOLD, 6), (THRESHOLD, 11)] + ([(otsu, 6)] if abs(otsu - THRESHOLD) > 12 else [])
    with ThreadPoolExecutor(max_workers=len(variants)) as ex:  # cada leitura é um processo do Tesseract
        results = list(ex.map(lambda v: _tesseract(pix, *v), variants))

    def score(words):
        return sum(w[5] for w in words if w[5] >= 60 and any(ch.isalnum() for ch in w[4]))

    return max(results, key=score)


def _tesseract(pix, thr: int, psm: int = 6):
    import pymupdf

    table = bytes(0 if v < thr else 255 for v in range(256))
    bw = pymupdf.Pixmap(pymupdf.csGRAY, pix.width, pix.height, pix.samples.translate(table), False)
    with tempfile.TemporaryDirectory(prefix="ocr-") as tmp:
        bw.save(f"{tmp}/p.png")
        tsv = subprocess.run(["tesseract", f"{tmp}/p.png", "stdout", "-l", "por", "--psm", str(psm),
                              "-c", "preserve_interword_spaces=1", "tsv"],
                             capture_output=True, text=True, timeout=180).stdout
    k = 72.0 / DPI
    out = []
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or c[0] != "5" or not c[11].strip():
            continue
        conf = float(c[10])
        if conf < 0:
            continue
        x, y, w, h = (int(c[i]) for i in (6, 7, 8, 9))
        out.append((x * k, y * k, (x + w) * k, (y + h) * k, c[11].strip(), conf))
    return out


def _otsu(samples: bytes) -> int:
    """Limiar preto/branco ideal da página (método de Otsu): folhas escuras ou claras ficam legíveis."""
    hist = [0] * 256
    for v, n in Counter(samples[::7]).items():
        hist[v] = n
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    w_b = sum_b = 0
    best, thr = -1.0, THRESHOLD
    for i in range(256):
        w_b += hist[i]
        if not w_b or w_b == total:
            continue
        sum_b += i * hist[i]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / (total - w_b)
        between = w_b * (total - w_b) * (m_b - m_f) ** 2
        if between > best:
            best, thr = between, i
    return max(110, min(215, thr + 10))


def _is_stamp(text: str) -> bool:
    t = plain(text)
    return "assinado digitalmente" in t or t.startswith("data: 20")


def page_lines(page) -> tuple[list[dict], bool]:
    """Linhas da página: [{y, x0, x1, texto, chunks:[{t, b:[x0,y0,x1,y1], c}]}]. Devolve também se usou OCR."""
    words = _words_from_text_layer(page)
    real = " ".join(w[4] for w in words)
    used_ocr = len(re.sub(r"assinado digitalmente.*?-03:00", "", plain(real), flags=re.S).strip()) < 60
    if used_ocr:
        words = _words_from_ocr(page)
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur = [], []
    for w in words:
        if cur and abs((w[1] + w[3]) / 2 - (cur[-1][1] + cur[-1][3]) / 2) > max(4.0, (w[3] - w[1]) * 0.6):
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        avg_h = sum(w[3] - w[1] for w in ln) / len(ln)
        chunks, ch = [], [ln[0]]
        for w in ln[1:]:
            if w[0] - ch[-1][2] > max(12.0, avg_h * 1.6):  # espaço grande = outra coluna
                chunks.append(ch)
                ch = []
            ch.append(w)
        chunks.append(ch)
        cs = [{"t": " ".join(w[4] for w in c), "b": [min(w[0] for w in c), min(w[1] for w in c),
                                                    max(w[2] for w in c), max(w[3] for w in c)],
               "c": round(sum(w[5] for w in c) / len(c), 1),
               "w": [[round(w[0], 1), round(w[2], 1), w[4]] for w in c]} for c in chunks]
        text = "   ".join(c["t"] for c in cs)
        if _is_stamp(text):
            continue
        out.append({"y": round(min(w[1] for w in ln), 1), "x0": cs[0]["b"][0], "texto": text, "chunks": cs})
    return out, used_ocr


# ================================================================== classificação
FILE_HINTS = [("tempo de contribui", "CTC"), ("ctc", "CTC"), ("historico funcional", "HISTORICO_FUNCIONAL"),
              ("ficha funcional", "HISTORICO_FUNCIONAL"), ("contracheque", "CONTRACHEQUE"),
              ("demonstrativo", "CONTRACHEQUE"), ("rg e cpf", "RG_CPF"), ("identidade", "RG_CPF"),
              ("requerimento", "REQUERIMENTO"), ("publica", "PUBLICACAO"), ("memoria de calculo", "MEMORIA_CALCULO"),
              ("acumula", "DECLARACAO_ACUMULACAO"), ("regencia", "DECLARACAO_REGENCIA"), ("obito", "CERTIDAO_OBITO"),
              ("casamento", "CERTIDAO_CASAMENTO"), ("nascimento", "CERTIDAO_NASCIMENTO"), ("ficha financeira", "FICHA_FINANCEIRA"),
              ("residencia", "COMPROVANTE_RESIDENCIA"), ("laudo", "LAUDO_MEDICO"), ("ato", "ATO"), ("portaria", "ATO")]
CONTENT_HINTS = [
    (r"certid.o de tempo de contribui", "CTC", 5), (r"historico funcional|ficha funcional", "HISTORICO_FUNCIONAL", 5),
    (r"demonstrativo de pagamento|total liquido|contracheque", "CONTRACHEQUE", 4),
    (r"memoria de calculo|minuta", "MEMORIA_CALCULO", 4), (r"certid.o de obito", "CERTIDAO_OBITO", 5),
    (r"certid.o de casamento", "CERTIDAO_CASAMENTO", 5), (r"certid.o de nascimento", "CERTIDAO_NASCIMENTO", 4),
    (r"acumula", "DECLARACAO_ACUMULACAO", 3), (r"regencia|efetivo exercicio .{0,40}magisterio", "DECLARACAO_REGENCIA", 3),
    (r"registro geral|carteira de identidade|republica federativa", "RG_CPF", 3), (r"\brequer", "REQUERIMENTO", 2),
    (r"\bresolve\b|portaria\s+n", "ATO", 2), (r"publicad|boletim|diario oficial|jornal", "PUBLICACAO", 2),
    (r"\bart\.?\s*\d+|\bartigo\s+\d+|\bparagrafo\b|\binciso\b|\u00a7", "LEGISLACAO", 2),
]


def _file_hint(file_name: str) -> str | None:
    f = plain(file_name)
    for key, typ in FILE_HINTS:
        if re.search(rf"\b{key}", f):  # palavra inteira ("comprobatorios" n\u00e3o \u00e9 "ato")
            return typ
    return None


def classify(file_name: str, text: str) -> str:
    t = plain(text)
    hint = _file_hint(file_name)
    arts = len(re.findall(r"\bart\.?\s*\d+|\u00a7|\binciso\b", t))
    if not hint and (arts >= 3 or (len(t) > 800 and arts >= 2)):  # texto legal
        return "LEGISLACAO"
    scores = {}
    for rx, typ, w in CONTENT_HINTS:
        n = len(re.findall(rx, t))
        if n:
            scores[typ] = scores.get(typ, 0) + w * min(n, 15 if typ == "LEGISLACAO" else 5)
    if hint:  # o nome que a equipe deu ao arquivo pesa mais que palavras soltas
        scores[hint] = scores.get(hint, 0) + 40
    return max(scores, key=scores.get) if scores else "OUTRO"


# ================================================================== extração por rótulo
def _date(s: str) -> str | None:
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4}|\d{2})\b", s)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y = y + (2000 if y < 50 else 1900) if y < 100 else y
    else:
        m = re.search(r"(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})", plain(s))
        if not m or m[2] not in MONTHS:
            return None
        d, mo, y = int(m[1]), MONTHS[m[2]], int(m[3])
    try:
        return date(y, mo, d).isoformat() if 1900 <= y <= 2100 else None
    except ValueError:
        return None


def _money(s: str) -> str | None:
    m = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", s)
    return m[0].replace(".", "").replace(",", ".") if m else None


def _pis_ok(d: str) -> bool:
    if len(d) != 11 or len(set(d)) == 1:
        return False
    s = sum(int(a) * b for a, b in zip(d[:10], [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    r = 11 - s % 11
    return (0 if r in (10, 11) else r) == int(d[10])


def _doc_number(s: str, n: int, check) -> tuple[str | None, bool]:
    """CPF/PIS: tenta como está e com as trocas comuns do OCR. Devolve (dígitos, foi_corrigido)."""
    for cand in re.findall(r"[\dOoDQlI|i/SsBZzg][\dOoDQlI|i/SsBZzg.\-\s]{%d,%d}" % (n - 1, n + 6), s):
        raw = re.sub(r"[.\-\s]", "", cand)
        digits = re.sub(r"\D", "", raw)
        if len(digits) == n and check(digits):
            return digits, False
        fixed = re.sub(r"\D", "", raw.translate(FIX))
        if len(fixed) == n and check(fixed):
            return fixed, True
    return None, False


LABEL_WORDS = re.compile(
    r"^\W*(nome|matricula|cpf|cargo|quadro|nivel|classe|registro|endereco|complemento|bairro|cidade|cep|telefone|"
    r"carteira|orgao|expedi|emissao|uf\b|pis|titulo|zona|secao|naturalidade|estado civil|grau|data|processo|funcao|"
    r"local|conta|periodo|vinculo|motivo|organograma|grupo|certificado|serie|filiacao|sexo|codigo|margem|referencia|"
    r"vencimento|desconto|descricao|ato e data|fonte|tempo|frequencia|deduc|lotacao|admissao|nascimento|natur)")


def _text(s: str) -> str | None:
    s = re.sub(r"^[\s:;.,\-|\u201c\u201d\"(]+", "", s).strip()
    s = re.split(r"\s{3,}", s)[0].strip(" :;|\u201c\u201d\"()")
    letters = sum(ch.isalpha() for ch in s)
    if letters < 3 or letters < len(s) * 0.6 or LABEL_WORDS.match(plain(s)):
        return None
    return s.upper()


def _digits(s: str) -> str | None:
    m = re.search(r"\d[\d.\-/]*\d|\d", re.split(r"\s{3,}", s.strip(" :;|"))[0])
    d = re.sub(r"\D", "", m[0]) if m else ""
    return d if 1 <= len(d) <= 12 else None


KINDS = {"date": _date, "money": _money, "text": _text,
         "digits": _digits}


def _conf(chunk_conf: float, fixed=False) -> str:
    if chunk_conf >= 85 and not fixed:
        return "alta"
    return "media" if chunk_conf >= 60 else "baixa"


class Page:
    def __init__(self, number: int, lines: list[dict]):
        self.n, self.lines = number, lines


def _find(pages: list[Page], label: str, kind: str, n_digits=0, check=None, key_max=0):
    """Procura o rótulo; valor na mesma linha (depois do rótulo) ou no bloco logo abaixo, na mesma coluna."""
    rx = re.compile(f"(?:{label})" + r"\w*\.?", re.I)  # consome a palavra inteira ("expeditor")
    for pg in pages:
        for i, ln in enumerate(pg.lines):
            for ci, ch in enumerate(ln["chunks"]):
                m = rx.search(plain(ch["t"]))
                if not m:
                    continue
                cands = []
                rest = ch["t"][m.end():] if len(ch["t"]) >= m.end() else ""
                if rest.strip(" :;|-"):
                    cands.append((rest, ch))
                x0 = ch["b"][0]
                x1 = ln["chunks"][ci + 1]["b"][0] if ci + 1 < len(ln["chunks"]) else 100_000
                lab_mid = (ch["b"][0] + ch["b"][2]) / 2
                for nxt in pg.lines[i + 1:i + 2]:  # logo abaixo, na mesma coluna (o mais alinhado primeiro)
                    below = [c2 for c2 in nxt["chunks"]
                             if x0 - 20 <= (c2["b"][0] + c2["b"][2]) / 2 <= x1 or (c2["b"][0] <= x0 + 10 and c2["b"][2] >= x0)]
                    below.sort(key=lambda c2: abs((c2["b"][0] + c2["b"][2]) / 2 - lab_mid))
                    cands += [(c2["t"], c2) for c2 in below]
                if ci + 1 < len(ln["chunks"]):  # por último, o bloco ao lado
                    cands.append((ln["chunks"][ci + 1]["t"], ln["chunks"][ci + 1]))
                for text, src in cands:
                    if kind in ("cpf", "pis"):
                        v, fixed = _doc_number(text, 11, check)
                        if v:
                            return v, src, pg.n, _conf(src["c"], fixed)
                        continue
                    v = KINDS[kind](text)
                    if v and not (kind == "text" and rx.search(plain(v))):
                        if key_max and len(v) > key_max:
                            continue
                        return v, src, pg.n, _conf(src["c"])
    return None


LABELS = [
    ("pessoa.nome", r"\bnome(\s+do\s+(servidor|funcionario|requerente|segurado|interessad[oa]))?\s*:?\s*$|\bnome\s*:", "text"),
    ("pessoa.cpf", r"\bc\.?p\.?f\b", "cpf"),
    ("pessoa.data_nascimento", r"nascimento", "date"),
    ("pessoa.nome_mae", r"nome da mae|\bmae\s*:|filia", "text"),
    ("pessoa.nome_pai", r"nome do pai|\bpai\s*:", "text"),
    ("pessoa.estado_civil", r"estado civil", "text"),
    ("pessoa.escolaridade", r"grau de instrucao|escolaridade", "text"),
    ("pessoa.rg_numero", r"carteira de identidade|\bregistro geral|\brg\b", "digits"),
    ("pessoa.rg_orgao", r"org.o expedi", "text"),
    ("pessoa.rg_data", r"emiss.o da identidade|data de expedi", "date"),
    ("pessoa.pis_pasep", r"pis\s*/?\s*pasep|\bpis\b|nit\b", "pis"),
    ("vinculo.matricula", r"matr.cula(\s+efetivo)?", "digits"),
    ("vinculo.cargo", r"\bcargo\b|\bfuncao\b", "text"),
    ("vinculo.data_admissao", r"admiss.o", "date"),
    ("vinculo.carreira_nivel", r"\bnivel\b|\bclasse\b", "text"),
    ("contracheque.total_proventos", r"total (de )?(vencimentos|proventos)|total bruto", "money"),
    ("contracheque.total_descontos", r"total (de )?descontos", "money"),
    ("contracheque.liquido", r"(total )?liquido", "money"),
]
BY_TYPE = {
    "RG_CPF": {"pessoa.nome", "pessoa.cpf", "pessoa.data_nascimento", "pessoa.nome_mae", "pessoa.nome_pai",
               "pessoa.rg_numero", "pessoa.rg_orgao", "pessoa.rg_data"},
    "HISTORICO_FUNCIONAL": {"pessoa.nome", "pessoa.cpf", "pessoa.data_nascimento", "pessoa.nome_mae", "pessoa.nome_pai",
                            "pessoa.estado_civil", "pessoa.escolaridade", "pessoa.rg_numero", "pessoa.rg_orgao",
                            "pessoa.rg_data", "pessoa.pis_pasep", "vinculo.matricula", "vinculo.cargo",
                            "vinculo.data_admissao"},
    "CONTRACHEQUE": {"pessoa.nome", "pessoa.cpf", "pessoa.data_nascimento", "pessoa.pis_pasep", "vinculo.matricula",
                     "vinculo.cargo", "vinculo.data_admissao", "vinculo.carreira_nivel", "contracheque.total_proventos",
                     "contracheque.total_descontos", "contracheque.liquido"},
    "CTC": {"pessoa.nome", "pessoa.cpf", "vinculo.matricula", "vinculo.cargo"},
    "REQUERIMENTO": {"pessoa.nome", "pessoa.cpf", "vinculo.matricula"},
    "DECLARACAO_ACUMULACAO": {"pessoa.nome", "pessoa.cpf", "vinculo.matricula"},
    "DECLARACAO_REGENCIA": {"pessoa.nome", "pessoa.cpf", "vinculo.matricula"},
    "CERTIDAO_OBITO": {"pessoa.nome", "pessoa.cpf", "pessoa.data_nascimento"},
}


def _field(key, value, src, page, conf, label=""):
    from .reader import FIELDS

    return {"chave": key, "rotulo": label or FIELDS.get(key, key), "valor": value, "pagina": page,
            "trecho": src["t"][:120] if src else "", "confianca": conf, "caixa": src["b"] if src else None}


def _search(pages, rx):
    for pg in pages:
        for ln in pg.lines:
            m = re.search(rx, plain(ln["texto"]))
            if m:
                return m, ln, pg.n
    return None


def _first_chunk(ln):
    return {"t": ln["texto"], "b": [ln["chunks"][0]["b"][0], ln["chunks"][0]["b"][1], ln["chunks"][-1]["b"][2],
                                    max(c["b"][3] for c in ln["chunks"])],
            "c": sum(c["c"] for c in ln["chunks"]) / len(ln["chunks"])}


def _column_centers(pages, names: dict, anchor: str):
    """Centros das colunas de uma tabela (pelo cabeçalho perto da linha que contém `anchor`)."""
    for pg in pages:
        for i, ln in enumerate(pg.lines):
            if re.search(anchor, plain(ln["texto"])):
                cols = {}
                for near in pg.lines[max(0, i - 2):i + 3]:
                    for ch in near["chunks"]:
                        for x0, x1, word in ch.get("w") or [[ch["b"][0], ch["b"][2], ch["t"]]]:
                            for key, rx in names.items():
                                if key not in cols and re.search(rx, plain(word)):
                                    cols[key] = (x0 + x1) / 2
                return cols, pg.n, i
    return {}, None, None


def _nearest(cols: dict, x: float):
    return min(cols, key=lambda k: abs(cols[k] - x)) if cols else None


def _ctc(pages, fields):
    m = _search(pages, r"tempo de contribui\S*\s+n\S*\s*([\d./-]+)")
    if m:
        fields.append(_field("ctc.numero", m[0][1], _first_chunk(m[1]), m[2], _conf(_first_chunk(m[1])["c"])))
    m = _search(pages, r"(\d{2}/\d{2}/\d{4})\s*(?:a|ate)\s*(\d{2}/\d{2}/\d{4})")
    if m:
        src = _first_chunk(m[1])
        fields.append(_field("ctc.periodo_inicio", _date(m[0][1]), src, m[2], _conf(src["c"])))
        fields.append(_field("ctc.periodo_fim", _date(m[0][2]), src, m[2], _conf(src["c"])))
    hit = _find(pages, r"org.o expedi", "text")
    if hit:
        fields.append(_field("ctc.orgao_emissor", hit[0], hit[1], hit[2], hit[3]))
    hit = _find(pages, r"local e data", "date")
    if hit:
        fields.append(_field("ctc.data_emissao", hit[0], hit[1], hit[2], hit[3]))
    text = " ".join(plain(ln["texto"]) for pg in pages for ln in pg.lines)
    rg = "RGPS" if re.search(r"\binss\b|regime geral", text) else "RPPS"
    fields.append(_field("ctc.regime_origem", rg, None, pages[0].n, "media"))

    cols, _, _ = _column_centers(pages, {"bruto": r"bruto", "faltas": r"falta", "licencas": r"licen",
                                         "suspensoes": r"suspens", "outras": r"outra", "soma": r"soma",
                                         "liquido": r"liquido"}, r"falta|deduc")
    if "liquido" not in cols:
        cols.pop("liquido", None)
    rows, total = [], None
    for pg in pages:
        for ln in pg.lines:
            t = plain(ln["texto"]).strip(" |—-")
            # o OCR às vezes põe "sujeira" curta antes do ano ("prt 2024 365 ...") — ignora até 4 letras/sinais
            t = re.sub(r"^[^\w]*(?:[a-z]{1,4})?[^\w\d]+(?=(?:19|20)\d{2}\b|\d{2}/\d{2})", "", t)
            per = re.match(r"^(\d{2}/\d{2}\s*a\s*\d{2}/\d{2}/\d{2,4}|(?:19|20)\d{2})\b", t)
            is_total = re.match(r"^(v\.?\s*a\s*transportar|total|soma geral)", t)
            if not per and not is_total:
                continue
            vals = {}
            for ch in ln["chunks"]:
                for tok in ch["t"].split():
                    if per and tok in per[1].split():
                        continue
                    num = 0 if re.fullmatch(r"[-–—]+", tok) else (int(re.sub(r"\D", "", tok)) if re.fullmatch(r"\d[\d.]*", tok) else None)
                    if num is None or not cols:
                        continue
                    key = _nearest(cols, (ch["b"][0] + ch["b"][2]) / 2)
                    vals.setdefault(key, num)
            if is_total:
                total = (vals, ln, pg.n)
                continue
            if per[1].isdigit() and not vals:
                continue
            rows.append({"periodo": per[1], "bruto": vals.get("bruto"), "faltas": vals.get("faltas", 0),
                         "licencas": vals.get("licencas", 0), "suspensoes": vals.get("suspensoes", 0),
                         "outras": vals.get("outras", 0), "liquido": vals.get("liquido"), "pagina": pg.n})
    apurado = _find(pages, r"tempo liquido apurado|tempo total de contribui\S* apurad|aposentadoria\s*:", "digits")
    if apurado:
        fields.append(_field("ctc.total_liquido_dias", apurado[0], apurado[1], apurado[2], apurado[3],
                             "Tempo líquido apurado no órgão (dias)"))
    for r in rows:
        # Ano inteiro tem 365/366 dias: número fora disso é erro de OCR (ex.: 369, ou líquido 264 no lugar de 364).
        # O sistema ajusta pelo que é plausível e marca a linha como "suspeita" para a equipe confirmar com a página.
        if re.fullmatch(r"(?:19|20)\d{2}", r["periodo"]):
            ded = sum(r[k] or 0 for k in ("faltas", "licencas", "suspensoes", "outras"))
            if r["bruto"] is not None and r["bruto"] > 366 and r["liquido"] is not None and r["liquido"] + ded <= 366:
                r["bruto"], r["suspeito"] = r["liquido"] + ded, True
            if r["bruto"] in (365, 366) and r["liquido"] is not None and abs(r["bruto"] - ded - r["liquido"]) >= 90:
                # dígito trocado (264 → 364): tenta trocar o primeiro dígito por um valor plausível (até 60 dias de falta)
                cands = [int(d + str(r["liquido"])[1:]) for d in "123" if len(str(r["liquido"])) == 3]
                ok = [c for c in cands if r["bruto"] - 60 <= c <= r["bruto"]]
                r["liquido"] = ok[0] if ok else r["bruto"] - ded
                r["suspeito"] = True
            if r["bruto"] in (365, 366) and r["liquido"] is None:  # líquido não lido: o mais provável, a conferir
                r["liquido"], r["suspeito"] = r["bruto"] - ded, True
    for r in rows:  # o OCR perde dígitos isolados nas colunas de dedução: deduz pela diferença (a conferir)
        if r["bruto"] and r["liquido"] is not None and not any(r[k] for k in ("faltas", "licencas", "suspensoes", "outras")):
            diff = r["bruto"] - r["liquido"]
            if 0 < diff <= 60:
                r["faltas"] = diff
    if total:
        vals, ln, pn = total
        if apurado:
            vals = {k: v for k, v in vals.items() if k != "liquido"}
        src = _first_chunk(ln)
        for key, k in (("bruto", "ctc.total_bruto_dias"), ("soma", "ctc.total_deducoes_dias"), ("liquido", "ctc.total_liquido_dias")):
            if vals.get(key) is not None:
                fields.append(_field(k, str(vals[key]), src, pn, _conf(src["c"])))
    return rows


def _payslip(pages, fields, doc_type):
    rubs = []
    m = _search(pages, r"(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+(?:de\s+)?(\d{4})")
    if m and doc_type == "CONTRACHEQUE":
        src = _first_chunk(m[1])
        fields.append(_field("contracheque.competencia", f"{m[0][2]}-{MONTHS[m[0][1]]:02d}", src, m[2], _conf(src["c"])))
        text = " ".join(plain(ln["texto"]) for pg in pages for ln in pg.lines)
        fields.append(_field("contracheque.situacao", "inativo" if re.search(r"inativ|aposentad|provento", text) else "ativo",
                             None, pages[0].n, "media"))
    cols, head_page, head_idx = _column_centers(pages, {"ref": r"refer", "prov": r"venc|provent", "desc": r"descont"},
                                                r"descri")
    for pg in pages:
        lines = [dict(ln, chunks=list(ln["chunks"])) for ln in pg.lines]
        if doc_type == "CONTRACHEQUE" and head_page is not None:
            if pg.n != head_page:
                continue
            lines = lines[head_idx + 1:]
            end = next((k for k, ln in enumerate(lines) if re.search(r"\btotal", plain(ln["texto"]))), len(lines))
            lines = lines[:end]
        for i, ln in enumerate(lines):  # "812,33" numa linha e "1058 I.R.R.F." na seguinte (ou anterior)
            if re.match(r"^\d{3,5}\s", ln["texto"].strip(" |")) and not any(_money(c["t"]) for c in ln["chunks"]):
                for j in (i - 1, i + 1):
                    if 0 <= j < len(lines) and any(_money(c["t"]) for c in lines[j]["chunks"]) and \
                            all(_money(c["t"]) or not c["t"].strip(" |") for c in lines[j]["chunks"]):
                        ln["chunks"] = ln["chunks"] + [c for c in lines[j]["chunks"] if _money(c["t"])]
                        lines[j]["chunks"] = []
                        break
        for ln in lines:
            if not ln["chunks"]:
                continue
            t = " ".join(c["t"] for c in ln["chunks"]).strip(" |")
            code = re.match(r"^(\d{3,5})\s+(.+)", t) if doc_type == "CONTRACHEQUE" else None
            moneys = [(ch, _money(ch["t"])) for ch in ln["chunks"] if _money(ch["t"])]
            if not moneys:
                continue
            first = ln["chunks"][0]["t"]
            if doc_type == "CONTRACHEQUE":
                if not code:
                    continue
                desc = re.split(r"\s{3,}|\d", code[2])[0].strip(" *|[")
                for ch, val in moneys:
                    x = (ch["b"][0] + ch["b"][2]) / 2
                    col = _nearest(cols, x) if cols else "prov"
                    if col == "desc" and "prov" not in cols and x < cols["desc"] - 60:
                        col = "prov"
                    if col == "ref":
                        continue
                    rubs.append({"codigo": code[1], "descricao": desc, "referencia": "", "valor": val,
                                 "natureza": "desconto" if col == "desc" else "provento", "pagina": pg.n})
            else:  # memória de cálculo / ficha: "Descrição .... valor"
                label = plain(first)
                if re.match(r"^total", label):
                    src = moneys[-1][0]
                    if not any(f["chave"] == "calculo.valor_total" for f in fields):
                        fields.append(_field("calculo.valor_total", moneys[-1][1], src, pg.n, _conf(src["c"])))
                    continue
                if _text(first) and not re.match(r"^(salario|proventos|valor|fundamenta)", label):
                    rubs.append({"codigo": "", "descricao": first.strip()[:80], "referencia": "", "valor": moneys[-1][1],
                                 "natureza": "provento", "pagina": pg.n})
    if doc_type == "MEMORIA_CALCULO":  # a minuta repete o quadro (mês anterior e posterior): fica o primeiro
        seen, uniq = set(), []
        for r in rubs:
            if r["descricao"] not in seen:
                seen.add(r["descricao"])
                uniq.append(r)
        rubs = uniq
    return rubs


def _dates_doc(pages, fields, doc_type):
    keys = {"REQUERIMENTO": "requerimento.data", "ATO": "ato.data", "PUBLICACAO": "publicacao.data"}
    if doc_type in keys:
        for pg in reversed(pages):
            for ln in reversed(pg.lines):
                d = _date(ln["texto"])
                if d:
                    src = _first_chunk(ln)
                    fields.append(_field(keys[doc_type], d, src, pg.n, _conf(src["c"])))
                    break
            else:
                continue
            break
    if doc_type == "ATO":
        m = _search(pages, r"portaria\s*(?:n\S*\s*)?([\d.]+\s*/\s*\d{2,4})")
        if m:
            src = _first_chunk(m[1])
            fields.append(_field("ato.numero", m[0][1].replace(" ", ""), src, m[2], _conf(src["c"])))
    if doc_type == "DECLARACAO_REGENCIA":
        per = []
        for pg in pages:
            for ln in pg.lines:
                for a, b in re.findall(r"(\d{2}/\d{2}/\d{4})\s*(?:a|ate|à)\s*(\d{2}/\d{2}/\d{4})", ln["texto"]):
                    per.append((_date(a), _date(b), ln, pg.n))
        per = [p for p in per if p[0] and p[1]]
        if per:
            first, last = min(per, key=lambda p: p[0]), max(per, key=lambda p: p[1])
            fields.append(_field("regencia.periodo_inicio", first[0], _first_chunk(first[2]), first[3], "media"))
            fields.append(_field("regencia.periodo_fim", last[1], _first_chunk(last[2]), last[3], "media"))
    if doc_type == "DECLARACAO_ACUMULACAO":
        m = _search(pages, r"(nao\s+acumul\w*|\bacumul\w*)")
        if m:
            src = _first_chunk(m[1])
            fields.append(_field("declaracao.acumula", "N" if m[0][1].startswith("nao") else "S", src, m[2], "baixa"))


def extract(file_name: str, pages_data: list[dict]) -> dict:
    """pages_data: [{n, linhas, ocr}] -> {"documentos": [...]} no formato da leitura por IA."""
    from .reader import DOC_TYPES

    groups = []
    for p in pages_data:
        text = " ".join(ln["texto"] for ln in p["linhas"])
        typ = classify(file_name, text)
        strong = any(re.search(rx, plain(text)) for rx, t, w in CONTENT_HINTS if w >= 3 and t == typ)
        if groups and (typ == groups[-1]["tipo"] or (not strong and typ in ("OUTRO", "LEGISLACAO") and
                                                       groups[-1]["tipo"] not in ("OUTRO", "LEGISLACAO"))):
            groups[-1]["pages"].append(p)
        else:
            groups.append({"tipo": typ, "pages": [p]})
    docs = []
    for g in groups:
        pages = [Page(p["n"], p["linhas"]) for p in g["pages"]]
        typ, fields, freq, rubs = g["tipo"], [], [], []
        title = next((ln["texto"].strip()[:120] for pg in pages for ln in pg.lines[:12]
                      if len(ln["texto"].strip()) > 12 and sum(c.isalpha() for c in ln["texto"]) > 10), DOC_TYPES[typ])
        if typ != "LEGISLACAO":
            for key, label, kind in LABELS:
                if key not in BY_TYPE.get(typ, {"pessoa.nome", "pessoa.cpf"}):
                    continue
                check = is_valid_cpf if kind == "cpf" else (_pis_ok if kind == "pis" else None)
                hit = _find(pages, label, kind, check=check, key_max=10 if key == "vinculo.matricula" else 0)
                if hit:
                    fields.append(_field(key, hit[0], hit[1], hit[2], hit[3]))
            if typ == "CTC":
                freq = _ctc(pages, fields)
            if typ in ("CONTRACHEQUE", "MEMORIA_CALCULO", "FICHA_FINANCEIRA"):
                rubs = _payslip(pages, fields, typ)
            _dates_doc(pages, fields, typ)
        ocr_pages = sum(1 for p in g["pages"] if p["ocr"])
        low = sum(1 for f in fields if f["confianca"] == "baixa")
        docs.append({
            "tipo": typ, "titulo": title, "pagina_inicial": g["pages"][0]["n"], "pagina_final": g["pages"][-1]["n"],
            "legibilidade": "boa" if not ocr_pages or (fields and low <= len(fields) / 4) else "regular",
            "observacoes": ("Lido por OCR local (folhas digitalizadas): confira os valores com a página. " if ocr_pages else "")
            + ("Texto legal: dados não extraídos." if typ == "LEGISLACAO" else ""),
            "campos": fields, "frequencia": freq, "rubricas": rubs})
    return {"documentos": docs}
