"""
CNAB 240 — padrão FEBRABAN para pagamentos (crédito em conta), segmentos A e B, e leitura do retorno.

É o leiaute GENÉRICO da FEBRABAN. Cada banco tem particularidades (versão do leiaute, tipo de serviço, campos
reservados, finalidade de TED): o arquivo precisa ser HOMOLOGADO com o banco antes do uso em produção. As
versões e o tipo de serviço são configuráveis por conta (TreasuryAccount).

Lotes: um para créditos no MESMO banco da conta pagadora (forma 01 — crédito em conta corrente) e outro para
contas em OUTROS bancos (forma 41 — TED para outra titularidade, câmara 018).
"""
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from apps.core.validators import only_digits

OCCURRENCES = {
    "00": "Crédito efetuado", "BD": "Inclusão efetuada com sucesso (agendado)", "AA": "Controle inválido",
    "AB": "Tipo de operação inválido", "AC": "Tipo de serviço inválido", "AD": "Forma de lançamento inválida",
    "AE": "Tipo/número de inscrição inválido", "AF": "Código de convênio inválido",
    "AG": "Agência/conta/DV da empresa inválido", "AH": "Nº sequencial do registro inválido",
    "AI": "Código de segmento inválido", "AJ": "Tipo de movimento inválido",
    "AK": "Câmara de compensação do favorecido inválida", "AL": "Banco do favorecido inválido",
    "AM": "Agência do favorecido inválida", "AN": "Conta/DV do favorecido inválido",
    "AO": "Nome do favorecido não informado", "AP": "Data de lançamento inválida", "AR": "Valor do lançamento inválido",
    "BC": "Nosso número inválido", "HA": "Lote não aceito", "HD": "Conta encerrada ou bloqueada",
}


def alpha(value, size: int) -> str:
    s = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper()
    return s[:size].ljust(size)


def num(value, size: int) -> str:
    s = only_digits(str(value if value is not None else ""))
    return s[-size:].rjust(size, "0")


def cents(value: Decimal, size: int) -> str:
    return num(int((Decimal(value) * 100).quantize(Decimal("1"))), size)


def ddmmyyyy(d: date) -> str:
    return d.strftime("%d%m%Y")


@dataclass
class Payee:
    our_number: str
    name: str
    cpf: str
    bank: str
    branch: str
    branch_digit: str
    account: str
    account_digit: str
    amount: Decimal


def _check(line: str) -> str:
    assert len(line) == 240, f"Registro CNAB com {len(line)} posições"
    return line


def remessa(*, bank_code: str, cnpj: str, agreement: str, branch: str, branch_digit: str, account: str,
            account_digit: str, company: str, bank_name: str, nsa: int, payment_date: date, payees: list[Payee],
            service: str = "30", file_version: str = "089", batch_version: str = "045",
            now: datetime | None = None) -> tuple[str, dict]:
    now = now or datetime.now()
    bank = num(bank_code, 3)
    emp = (num(agreement, 20) if agreement.isdigit() else alpha(agreement, 20))
    acct = num(branch, 5) + alpha(branch_digit, 1) + num(account, 12) + alpha(account_digit[:1], 1) + \
        alpha(account_digit[1:2], 1)
    lines = [_check(
        bank + "0000" + "0" + " " * 9 + "2" + num(cnpj, 14) + emp + acct + alpha(company, 30) + alpha(bank_name, 30)
        + " " * 10 + "1" + ddmmyyyy(now) + now.strftime("%H%M%S") + num(nsa, 6) + num(file_version, 3) + "01600"
        + " " * 20 + " " * 20 + " " * 29)]
    groups = [("01", "000", [p for p in payees if num(p.bank, 3) == bank]),
              ("41", "018", [p for p in payees if num(p.bank, 3) != bank])]
    lot_no, total_lines, summary = 0, 0, {"lotes": [], "quantidade": 0, "total": "0.00"}
    grand = Decimal(0)
    for form, chamber, items in groups:
        if not items:
            continue
        lot_no += 1
        lot = num(lot_no, 4)
        lines.append(_check(
            bank + lot + "1" + "C" + num(service, 2) + form + num(batch_version, 3) + " " + "2" + num(cnpj, 14) + emp
            + acct + alpha(company, 30) + alpha("", 40) + alpha("", 30) + num("", 5) + alpha("", 15) + alpha("", 20)
            + num("", 5) + num("", 3) + alpha("", 2) + " " * 8 + " " * 10))
        seq, total = 0, Decimal(0)
        for p in items:
            seq += 1
            lines.append(_check(
                bank + lot + "3" + num(seq, 5) + "A" + "0" + "00" + chamber + num(p.bank, 3) + num(p.branch, 5)
                + alpha(p.branch_digit, 1) + num(p.account, 12) + alpha(p.account_digit[:1], 1)
                + alpha(p.account_digit[1:2], 1) + alpha(p.name, 30) + alpha(p.our_number, 20)
                + ddmmyyyy(payment_date) + "BRL" + num(0, 15) + cents(p.amount, 15) + " " * 20 + num(0, 8)
                + num(0, 15) + alpha("", 40) + alpha("", 2) + alpha("", 5) + alpha("", 2) + " " * 3 + "0"
                + " " * 10))
            seq += 1
            lines.append(_check(
                bank + lot + "3" + num(seq, 5) + "B" + " " * 3 + "1" + num(p.cpf, 14) + alpha("", 30) + num("", 5)
                + alpha("", 15) + alpha("", 15) + alpha("", 20) + num("", 5) + alpha("", 3) + alpha("", 2)
                + ddmmyyyy(payment_date) + cents(p.amount, 15) + num(0, 15) + num(0, 15) + num(0, 15) + num(0, 15)
                + alpha("", 15) + "0" + num("", 6) + num("", 8)))
            total += Decimal(p.amount)
        lines.append(_check(
            bank + lot + "5" + " " * 9 + num(seq + 2, 6) + cents(total, 18) + num(0, 18) + num(0, 6) + " " * 165
            + " " * 10))
        total_lines += seq + 2
        grand += total
        summary["lotes"].append({"lote": lot_no, "forma": "Crédito em conta (mesmo banco)" if form == "01" else "TED",
                                 "quantidade": len(items), "total": f"{total:.2f}"})
    lines.append(_check(bank + "9999" + "9" + " " * 9 + num(lot_no, 6) + num(total_lines + 2, 6) + num(0, 6)
                        + " " * 205))
    summary.update({"quantidade": len(payees), "total": f"{grand:.2f}"})
    return "\r\n".join(lines) + "\r\n", summary


def parse_return(content: str) -> list[dict]:
    """Segmentos A do retorno: seu número, valor, data e ocorrências."""
    out = []
    for raw in content.splitlines():
        line = raw.rstrip("\r\n")
        if len(line) < 240 or line[7] != "3" or line[13] != "A":
            continue
        codes = [line[230 + i:232 + i].strip() for i in range(0, 10, 2)]
        codes = [c for c in codes if c]
        value = Decimal(int(line[119:134] or "0")) / 100
        out.append({"our_number": line[73:93].strip(), "amount": value, "codes": codes,
                    "message": "; ".join(f"{c} — {OCCURRENCES.get(c, 'ocorrência do banco')}" for c in codes)})
    return out
