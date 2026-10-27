"""
Catálogo de relatórios. Cada relatório declara o módulo de permissão (relatorios.*), os filtros e uma função que
devolve colunas, linhas e totais. A tela, a impressão e a exportação (Excel/CSV) são genéricas.

Tipos de coluna: text, int, money (Decimal), date, percent, bool.
Tipos de filtro: competencia (AAAA-MM), ano, data, select (com options), plano (Financeiro/Previdenciário/Compra
de Vidas).
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable

REPORTS: dict[str, "Report"] = {}

PLANO_FILTER = {"key": "plano", "label": "Folha / massa", "type": "select", "default": "",
                "options": [["", "Todas"], ["FINANCEIRO", "Financeiro"], ["PREVIDENCIARIO", "Previdenciário"],
                            ["COMPRA_VIDAS", "Compra de Vidas"]]}


@dataclass
class Report:
    code: str
    module: str
    title: str
    description: str
    run: Callable
    filters: list = field(default_factory=list)
    landscape: bool = False
    also: tuple = ()  # outras telas (módulos) onde o relatório também aparece, cada uma com a sua permissão

    @property
    def modules(self) -> tuple:
        return (self.module, *self.also)

    def meta(self) -> dict:
        return {"codigo": self.code, "modulo": self.module, "titulo": self.title, "descricao": self.description,
                "filtros": self.filters, "paisagem": self.landscape}


def report(code: str, module: str, title: str, description: str, filters=None, landscape=False, also=()):
    def deco(fn):
        REPORTS[code] = Report(code, module, title, description, fn, filters or [], landscape, tuple(also))
        return fn
    return deco


def col(key: str, label: str, kind: str = "text") -> dict:
    return {"key": key, "label": label, "tipo": kind}


def result(columns: list, rows: list, totals: dict | None = None, notes: list | None = None) -> dict:
    return {"colunas": columns, "linhas": rows, "totais": totals or {}, "observacoes": notes or []}


def jsonable(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v
