"""Filtro de logs que mascara dados sensíveis (CPF, senhas, tokens)."""
import logging
import re

_CPF_RE = re.compile(r"\b(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})\b")
_SECRET_RE = re.compile(
    r"(?i)(password|senha|token|secret|authorization)([\"']?\s*[:=]\s*[\"']?)([^\s\"',}]+)"
)


def mask_text(text: str) -> str:
    text = _CPF_RE.sub(r"***.\2.\3-**", text)
    text = _SECRET_RE.sub(r"\1\2********", text)
    return text


class MaskSensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        masked = mask_text(message)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True
