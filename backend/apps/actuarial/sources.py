"""
Origens de dados da base atuarial.

Cada arquivo do leiaute (servidores, aposentados, ...) é alimentado por uma
função registrada com @source. A função recebe o contexto da geração e
devolve as linhas com as variáveis do leiaute oficial, mais as chaves de
controle:

    "_massa": Segment da pessoa (FINANCEIRO / PREVIDENCIARIO / COMPRA_VIDAS)
    "_lote":  LifePurchase que transferiu a vida (obrigatório em COMPRA_VIDAS)

Os módulos de Cadastro (Fase 2), Concessão (Fase 4) e Folha (Fase 5)
registrarão aqui suas origens. Enquanto não existem, o arquivo é gerado
apenas com o cabeçalho oficial e a pendência é informada — nenhum dado é
simulado.
"""
from dataclasses import dataclass, field
from datetime import date

SOURCES: dict = {}

MISSING = {
    "servidores": "Cadastro de servidores e vínculos (Fase 2)",
    "aposentados": "Concessão de aposentadorias e folha (Fases 4 e 5)",
    "pensionistas": "Concessão de pensões e folha (Fases 4 e 5)",
    "dependentes": "Cadastro de dependentes (Fase 2)",
    "servidores_baixas": "Histórico funcional — desligamentos e óbitos (Fase 2)",
    "aposentados_baixas": "Eventos de cessação de aposentadorias (Fase 4)",
    "pensionistas_baixas": "Eventos de cessação de pensões (Fase 4)",
}


@dataclass
class SourceContext:
    institution: object
    segments: list
    reference_date: date        # último dia da competência da data-base
    period_start: date          # início do período das baixas (12 meses)
    period_end: date
    pendencias: list = field(default_factory=list)


def source(file_key: str):
    def decorator(fn):
        SOURCES[file_key] = fn
        return fn
    return decorator


def fetch(file_key: str, ctx: SourceContext) -> list[dict]:
    from .layouts import FILES

    fn = SOURCES.get(file_key)
    if fn is None:
        ctx.pendencias.append(
            f"{FILES[file_key][1]}: origem não implementada — {MISSING.get(file_key, 'módulo futuro')}. "
            "Arquivo gerado somente com o cabeçalho oficial."
        )
        return []
    return [r for r in fn(ctx) if r.get("_massa") in ctx.segments]
