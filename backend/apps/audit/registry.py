"""
Registro de modelos auditados automaticamente.

    register(MeuModelo, module="cadastros.segurados", exclude=["campo"])

Inclusões, alterações (somente campos alterados, com valor anterior e novo)
e exclusões passam a ser gravadas em audit_logs via sinais do Django.
"""
from dataclasses import dataclass, field

ALWAYS_EXCLUDED = {"updated_at", "updated_by", "created_at", "created_by"}
# Campos cujo conteúdo nunca é gravado (apenas indica-se que foi alterado)
REDACTED_FIELDS = {"password"}
REDACTED_MARK = "[protegido]"


@dataclass
class AuditConfig:
    module: str
    exclude: set = field(default_factory=set)
    redact: set = field(default_factory=set)


_registry: dict = {}


def register(model, module: str, exclude=None, redact=None) -> None:
    _registry[model] = AuditConfig(
        module=module,
        exclude=set(exclude or []) | ALWAYS_EXCLUDED,
        redact=set(redact or []) | REDACTED_FIELDS,
    )


def get_config(model) -> AuditConfig | None:
    return _registry.get(model)


def is_registered(model) -> bool:
    return model in _registry
