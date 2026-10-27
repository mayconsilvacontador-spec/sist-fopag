from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("financeiro/contas", views.TreasuryAccountViewSet, basename="treasury-account")
router.register("financeiro/lotes", views.PaymentBatchViewSet, basename="payment-batch")
router.register("financeiro/arquivos", views.BankFileViewSet, basename="bank-file")
router.register("financeiro/extrato", views.StatementViewSet, basename="statement-line")
router.register("financeiro/contabil", views.MappingViewSet, basename="accounting-mapping")
router.register("arrecadacao/contribuicoes", views.ContributionViewSet, basename="contribution")
router.register("arrecadacao/aportes", views.AporteViewSet, basename="aporte")
router.register("arrecadacao/parcelamentos", views.AgreementViewSet, basename="installment-agreement")
router.register("arrecadacao/receitas", views.RevenueViewSet, basename="revenue")

urlpatterns = router.urls + [
    path("arrecadacao/conciliacao/", views.ReconciliationView.as_view(), name="collection-reconciliation"),
    path("arrecadacao/divergencias/", views.DivergencesView.as_view(), name="collection-divergences"),
    path("arrecadacao/aliquotas/", views.RatesView.as_view(), name="collection-rates"),
]
