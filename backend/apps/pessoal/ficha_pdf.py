"""
Leitura de FICHA FINANCEIRA ANUAL em PDF (relatório com texto digital, uma página por ano: rubricas nas linhas,
Jan…Dez + 13º Salário + Total nas colunas, blocos PROVENTOS e DESCONTOS) — ex.: "ARFicha_Financeira_Sintetica".

Os números são alinhados à direita: cada valor vai para a coluna cujo título termina mais perto dele. Tudo é
CONFERIDO com o próprio relatório: soma dos meses × coluna Total de cada rubrica, soma das rubricas × linha
TOTAL PROVENTOS/DESCONTOS e proventos − descontos × LÍQUIDOS. Divergência vira aviso (nada é ajustado sozinho).
Devolve linhas no leiaute da tabela padrão (`ficha.COLUMNS`), gravadas por `ficha.import_lines`.
"""
import re
from decimal import Decimal, InvalidOperation

from apps.core.exceptions import BusinessRuleError

MONTHS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
NUM = re.compile(r"^-?[\d.]+,\d{2}$")


def _dec(s: str) -> Decimal | None:
    if not NUM.match(s):
        return None
    try:
        return Decimal(s.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _lines(page):
    """Palavras agrupadas por linha (tolerância de 3 pt na altura), em ordem da esquerda para a direita."""
    words = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows: list[list] = []
    for w in words:
        y = (w[1] + w[3]) / 2
        if rows and abs(rows[-1][0] - y) <= 3:
            rows[-1][1].append(w)
        else:
            rows.append([y, [w]])
    return [sorted(ws, key=lambda w: w[0]) for _, ws in rows]


def _header_cols(ws) -> list[tuple[str, float]] | None:
    """Linha de títulos (Jan … Dez, 13º Salário, Total) → [(coluna, borda direita)]."""
    cols = []
    for w in ws:
        t = w[4].upper().rstrip(".")
        if t in MONTHS:
            cols.append((t, w[2]))
        elif t.startswith("SAL") and cols and cols[-1][0] == "DEZ":
            cols.append(("13", w[2]))
        elif t == "TOTAL" and cols:
            cols.append(("TOTAL", w[2]))
    return cols if len(cols) >= 14 and [c for c, _ in cols[:12]] == MONTHS else None


def _values(ws, cols, label_end):
    out, bad = {}, []
    for w in ws:
        v = _dec(w[4])
        if w[0] < label_end and v is None:
            continue
        if v is None:
            bad.append(w[4])
            continue
        col = min(cols, key=lambda c: abs(c[1] - w[2]))[0]
        if col in out:
            bad.append(w[4])
        out[col] = v
    return out, bad


def _field(text: str, label: str) -> str:
    m = re.search(label + r"\s*:?\s*([^\n]+)", text)
    return m.group(1).strip() if m else ""


def parse(content: bytes) -> tuple[list[dict], list[str], dict]:
    import pymupdf

    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise BusinessRuleError("Não foi possível abrir o PDF.") from exc
    rows: list[dict] = []
    warnings: list[str] = []
    info = {"paginas": len(doc), "anos": []}
    for pno, page in enumerate(doc, start=1):
        text = page.get_text()
        if len(text.strip()) < 50:
            raise BusinessRuleError(f"Página {pno} sem texto (PDF digitalizado). Use a Leitura inteligente ou a tabela padrão.")
        m = re.search(r"ANO\s+DE\s+(\d{4})", text)
        if not m:
            raise BusinessRuleError(f"Página {pno}: não é uma ficha financeira anual (falta 'ANO DE AAAA').")
        year = int(m.group(1))
        cpf, reg = "", ""
        lines = _lines(page)
        for ws in lines:  # "Servidor:  12345.1 - NOME" e "CPF: 000.000.000-00" (rótulo e valor lado a lado)
            for i, w in enumerate(ws[:-1]):
                t = w[4].upper()
                if t.startswith("SERVIDOR") and not reg and re.fullmatch(r"[\d.\-/]+", ws[i + 1][4]):
                    reg = ws[i + 1][4]
                elif t.startswith("CPF") and not cpf:
                    nxt = ws[i + 1][4] if t in ("CPF", "CPF:") else t[4:]
                    cpf = re.sub(r"\D", "", nxt) if len(re.sub(r"\D", "", nxt)) == 11 else ""
        if not cpf:
            raise BusinessRuleError(f"Página {pno} ({year}): CPF do servidor não encontrado.")
        info.setdefault("cpf", cpf)
        if cpf != info["cpf"]:
            raise BusinessRuleError(f"Página {pno} ({year}): CPF diferente da primeira página — envie um servidor por arquivo.")
        info["anos"].append(year)
        info.setdefault("matricula", reg)
        nature, cols, label_end = None, None, 0.0
        sums: dict[str, dict[str, Decimal]] = {"PROVENTO": {}, "DESCONTO": {}}
        for ws in lines:
            first = ws[0][4].upper()
            hdr = _header_cols(ws)
            if hdr:
                cols = hdr
                label_end = min(w[0] for w in ws if w[4].upper() == "JAN") - 5
                nature = "PROVENTO" if first.startswith("PROVENTO") else "DESCONTO" if first.startswith("DESCONTO") else None
                continue
            if cols is None:
                continue
            lab = [w for w in ws if w[0] < label_end and _dec(w[4]) is None]
            label = " ".join(w[4] for w in lab).upper()
            if label.startswith("TOTAL") or label.startswith("LÍQUIDO") or label.startswith("LIQUIDO"):
                vals, _ = _values(ws, cols, label_end)
                kind = "PROVENTO" if "PROVENTO" in label else "DESCONTO" if "DESCONTO" in label else "LIQUIDO"
                if kind == "LIQUIDO":
                    for c, v in vals.items():
                        calc = sums["PROVENTO"].get(c, Decimal(0)) - sums["DESCONTO"].get(c, Decimal(0))
                        if calc != v:
                            warnings.append(f"{year} {c}: proventos − descontos = {calc} e o líquido do relatório é {v}.")
                else:
                    for c, v in vals.items():
                        if sums[kind].get(c, Decimal(0)) != v:
                            warnings.append(f"{year} {c}: soma das rubricas ({sums[kind].get(c, 0)}) diferente do "
                                            f"TOTAL {kind}S ({v}). Confira a leitura.")
                    nature = None
                continue
            if nature is None:
                continue
            if not lab or not re.fullmatch(r"\d+", lab[0][4]):
                continue
            code, name = lab[0][4], " ".join(w[4] for w in lab[1:])[:120]
            vals, bad = _values(ws, cols, label_end)
            if bad:
                warnings.append(f"{year} rubrica {code}: valores não reconhecidos {bad}.")
            months = sum((vals.get(c, Decimal(0)) for c in MONTHS + ["13"]), Decimal(0))
            if "TOTAL" in vals and months != vals["TOTAL"]:
                warnings.append(f"{year} rubrica {code} {name}: soma dos meses ({months}) ≠ total da linha ({vals['TOTAL']}).")
            for c, v in vals.items():
                sums[nature][c] = sums[nature].get(c, Decimal(0)) + v
            for i, mo in enumerate(MONTHS + ["13"]):
                v = vals.get(mo)
                if not v:
                    continue
                rows.append({"CPF": cpf, "MATRICULA": reg, "COMPETENCIA": f"{min(i + 1, 12):02d}/{year}",
                             "TIPO_FOLHA": "DECIMO" if mo == "13" else "MENSAL", "CODIGO": code, "RUBRICA": name,
                             "NATUREZA": nature[0], "VALOR": str(v), "CLASSIFICACAO": "",
                             "_ORIGEM": f"Página {pno} ({year}), rubrica {code}, {mo.title() if mo != '13' else '13º'}"})
    if not rows:
        raise BusinessRuleError("Nenhuma rubrica encontrada. O leiaute deste PDF não foi reconhecido — use a tabela padrão.")
    return rows, warnings, info
