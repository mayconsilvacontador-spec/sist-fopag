from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("comprev/processos", views.ProcessViewSet, basename="comprev-process")
router.register("comprev/movimentos", views.MovementViewSet, basename="comprev-movement")

urlpatterns = router.urls + [
    path("comprev/fluxo/", views.FlowView.as_view()),
    path("comprev/indicadores/", views.IndicatorsView.as_view()),
]
