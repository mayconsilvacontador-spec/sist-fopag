"""
Leiautes da base de dados para avaliação atuarial.

O leiaute SPREV é carregado do dicionário oficial convertido para JSON
(layouts/sprev_2021.json). A SPREV exige que os nomes e a ordem das variáveis
não sejam alterados — por isso nenhuma coluna extra é incluída nos arquivos
oficiais; a identificação da Compra de Vidas vai em arquivo complementar.
"""
import json
from functools import lru_cache
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parent / "layouts"
DEFAULT_LAYOUT = "SPREV_2021"

# Arquivo do leiaute -> (nome do arquivo gerado, rótulo, é arquivo de baixas)
FILES = {
    "servidores": ("SERVIDORES", "Servidores em atividade", False),
    "aposentados": ("APOSENTADOS", "Aposentados", False),
    "pensionistas": ("PENSIONISTAS", "Pensionistas", False),
    "dependentes": ("DEPENDENTES", "Dependentes", False),
    "servidores_baixas": ("SERV_FALEC_EXON", "Baixas de servidores", True),
    "aposentados_baixas": ("APOS_FALEC", "Baixas de aposentados", True),
    "pensionistas_baixas": ("PENS_FALEC", "Baixas de pensionistas", True),
}


@lru_cache
def load_layout(code: str = DEFAULT_LAYOUT) -> dict:
    path = LAYOUT_DIR / f"{code.lower()}.json"
    if not path.exists():
        raise ValueError(f"Leiaute {code} não encontrado.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def columns(file_key: str, code: str = DEFAULT_LAYOUT) -> list[dict]:
    return load_layout(code)["arquivos"][file_key]


def column_names(file_key: str, code: str = DEFAULT_LAYOUT) -> list[str]:
    return [c["nome"] for c in columns(file_key, code)]
