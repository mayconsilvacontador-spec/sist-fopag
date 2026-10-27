"""Leitura de extrato bancário OFX (1.x SGML ou 2.x XML): lançamentos STMTTRN."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from apps.core.exceptions import BusinessRuleError

_TRN = re.compile(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", re.S | re.I)


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}>([^<\r\n]*)", block, re.I)
    return m.group(1).strip() if m else ""


def parse(content: str) -> dict:
    if "<OFX>" not in content.upper():
        raise BusinessRuleError("Arquivo não parece ser um extrato OFX.")
    lines = []
    for block in _TRN.findall(content):
        try:
            amount = Decimal(_tag(block, "TRNAMT").replace(",", "."))
        except InvalidOperation:
            continue
        dt = _tag(block, "DTPOSTED")[:8]
        if len(dt) != 8:
            continue
        fitid = _tag(block, "FITID") or f"{dt}-{amount}-{len(lines)}"
        lines.append({"date": date(int(dt[:4]), int(dt[4:6]), int(dt[6:8])), "amount": amount, "fitid": fitid[:80],
                      "memo": (_tag(block, "MEMO") or _tag(block, "NAME"))[:255]})
    if not lines:
        raise BusinessRuleError("Nenhum lançamento encontrado no extrato.")
    return {"bank": _tag(content, "BANKID"), "account": _tag(content, "ACCTID"), "lines": lines}
