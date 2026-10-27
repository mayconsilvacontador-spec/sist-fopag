"""
Contexto da requisição corrente (usuário, IP, instituição, justificativa).

Usa contextvars, o que funciona corretamente tanto em WSGI (threads) quanto
em ASGI e em tarefas Celery. A auditoria lê estes valores para registrar
quem fez o quê e de onde.
"""
import contextvars
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Optional


@dataclass(frozen=True)
class RequestContext:
    user: Any = None
    ip: Optional[str] = None
    user_agent: str = ""
    institution_id: Optional[str] = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    justification: str = ""
    source: str = "web"  # web | celery | command


_context: contextvars.ContextVar[RequestContext] = contextvars.ContextVar(
    "sist_request_context", default=RequestContext(source="system")
)


def get_context() -> RequestContext:
    return _context.get()


def set_context(ctx: RequestContext):
    return _context.set(ctx)


def reset_context(token) -> None:
    _context.reset(token)


def update_context(**kwargs) -> None:
    _context.set(replace(_context.get(), **kwargs))


def get_current_user():
    return _context.get().user


@contextmanager
def audit_context(**kwargs):
    """
    Altera temporariamente o contexto. Exemplo:

        with audit_context(justification="Correção solicitada no processo X"):
            obj.save()
    """
    token = _context.set(replace(_context.get(), **kwargs))
    try:
        yield
    finally:
        _context.reset(token)
