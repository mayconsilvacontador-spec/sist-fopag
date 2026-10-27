from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    """Verificação simples de disponibilidade (sem dados sensíveis)."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db = "ok"
    except Exception:
        db = "erro"
    return JsonResponse({"status": "ok" if db == "ok" else "degradado", "database": db})


api_v1 = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.institutions.urls")),
    path("", include("apps.audit.urls")),
    path("", include("apps.alerts.urls")),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.search.urls")),
    path("", include("apps.actuarial.urls")),
    path("", include("apps.cadastros.urls")),
    path("", include("apps.people.urls")),
    path("", include("apps.employment.urls")),
    path("", include("apps.protocolo.urls")),
    path("", include("apps.previdencia.urls")),
    path("", include("apps.concessao.urls")),
    path("", include("apps.folha.urls")),
    path("", include("apps.esocial.urls")),
    path("", include("apps.financeiro.urls")),
    path("", include("apps.portal.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.provadevida.urls")),
    path("", include("apps.recadastramento.urls")),
    path("", include("apps.comprev.urls")),
    path("", include("apps.leitura.urls")),
    path("", include("apps.pessoal.urls")),
]

urlpatterns = [
    path("api/v1/", include(api_v1)),
    path("api/health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("django-admin/", admin.site.urls),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
