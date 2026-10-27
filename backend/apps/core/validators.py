"""Validadores de documentos brasileiros."""
import re

from django.core.exceptions import ValidationError


def only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def is_valid_cpf(value: str | None) -> bool:
    cpf = only_digits(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(cpf[i]) * (size + 1 - i) for i in range(size))
        digit = (total * 10) % 11
        if digit == 10:
            digit = 0
        if digit != int(cpf[size]):
            return False
    return True


def is_valid_cnpj(value: str | None) -> bool:
    cnpj = only_digits(value)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    weights_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_2 = [6] + weights_1
    for weights, pos in ((weights_1, 12), (weights_2, 13)):
        total = sum(int(cnpj[i]) * weights[i] for i in range(len(weights)))
        rest = total % 11
        digit = 0 if rest < 2 else 11 - rest
        if digit != int(cnpj[pos]):
            return False
    return True


def validate_cpf(value):
    if not is_valid_cpf(value):
        raise ValidationError("CPF inválido.")


def validate_cnpj(value):
    if not is_valid_cnpj(value):
        raise ValidationError("CNPJ inválido.")


def format_cpf(value: str | None) -> str:
    cpf = only_digits(value)
    if len(cpf) != 11:
        return value or ""
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def format_cnpj(value: str | None) -> str:
    c = only_digits(value)
    if len(c) != 14:
        return value or ""
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def mask_cpf(value: str | None) -> str:
    """CPF mascarado para exibição em logs/listagens: ***.456.789-**"""
    cpf = only_digits(value)
    if len(cpf) != 11:
        return ""
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"
