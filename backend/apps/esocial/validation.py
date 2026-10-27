"""
Validação contra os XSDs oficiais do eSocial.

Os esquemas não acompanham o SIST: baixe o pacote de leiautes no portal gov.br/esocial e copie os arquivos .xsd
para backend/apps/esocial/xsd/ (ex.: evtCdBenefIn.xsd, evtBenPrRP.xsd, ...). Sem eles, só a validação de
campos obrigatórios do SIST é feita — a situação na tela informa isso.
"""
from functools import lru_cache
from pathlib import Path

XSD_DIR = Path(__file__).resolve().parent / "xsd"


@lru_cache(maxsize=32)
def _schema(root_name: str):
    try:
        from lxml import etree
    except ImportError:
        return None
    if not XSD_DIR.exists():
        return None
    files = sorted(XSD_DIR.glob(f"*{root_name}*.xsd"))
    if not files:
        return None
    return etree.XMLSchema(etree.parse(str(files[0])))


def xsd_available(root_name: str) -> bool:
    return _schema(root_name) is not None


def validate_xsd(root_name: str, xml: str) -> list[str] | None:
    """Erros do XSD; None quando o XSD não está disponível."""
    schema = _schema(root_name)
    if schema is None:
        return None
    from lxml import etree

    doc = etree.fromstring(xml.encode("utf-8"))
    if schema.validate(doc):
        return []
    return [f"XSD: linha {e.line}: {e.message}" for e in schema.error_log][:20]
