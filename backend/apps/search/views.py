from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .registry import PROVIDERS


class GlobalSearchView(APIView):
    """GET /api/v1/search/?q=termo — resultados agrupados por tipo."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"

    def get(self, request):
        term = (request.query_params.get("q") or "").strip()[:100]
        if len(term) < 2:
            return Response({"q": term, "groups": []})
        keys = getattr(request, "permission_keys", set())
        groups = []
        for prov in PROVIDERS:
            if prov.permission not in keys:
                continue
            items = prov.fn(request, term, 6)
            if items:
                groups.append({"key": prov.key, "label": prov.label, "items": items})
        return Response({"q": term, "groups": groups})
