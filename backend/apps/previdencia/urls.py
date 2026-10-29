from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("previdencia/averbacoes", views.AverbacaoViewSet, basename="averbacao")
router.register("previdencia/salarios", views.ContributionSalaryViewSet, basename="contribution-salary")
router.register("previdencia/regras", views.RetirementRuleViewSet, basename="retirement-rule")
router.register("previdencia/ctc", views.CtcViewSet, basename="ctc")
router.register("previdencia/legislacao", views.LegalNormViewSet, basename="legal-norm")

urlpatterns = [
    path("previdencia/tempo/<uuid:pk>/", views.TimeView.as_view(), name="previdencia-tempo"),
    path("previdencia/simulacao/<uuid:pk>/", views.SimulationView.as_view(), name="previdencia-simulacao"),
    path("previdencia/fatores/", views.CorrectionFactorView.as_view(), name="previdencia-fatores"),
    path("previdencia/pacotes-regras/", views.RulePackagesView.as_view(), name="previdencia-pacotes"),
] + router.urls
