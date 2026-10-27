"""
Middleware que popula o contexto da requisição.

A autenticação JWT do DRF acontece dentro da view (não no middleware), por
isso o usuário é atualizado no contexto por
apps.accounts.permissions.attach_request_context.
"""
import uuid
from urllib.parse import unquote

from .context import RequestContext, reset_context, set_context
from .net import get_client_ip


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        # O frontend envia a justificativa codificada (cabeçalhos HTTP são ASCII)
        justification = unquote(request.headers.get("X-Justification") or "")[:1000]
        user = getattr(request, "user", None)
        ctx = RequestContext(
            user=user if getattr(user, "is_authenticated", False) else None,
            ip=get_client_ip(request),
            user_agent=(request.headers.get("User-Agent") or "")[:400],
            institution_id=request.headers.get("X-Institution-Id") or None,
            request_id=request_id[:64],
            justification=justification,
            source="web",
        )
        token = set_context(ctx)
        try:
            response = self.get_response(request)
        finally:
            reset_context(token)
        response["X-Request-Id"] = ctx.request_id
        return response
