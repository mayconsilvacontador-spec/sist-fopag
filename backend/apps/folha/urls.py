from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("folha/rubricas", views.RubricViewSet, basename="payroll-rubric")
router.register("folha/consignatarias", views.ConsigneeViewSet, basename="payroll-consignee")
router.register("folha/diferencas", views.AdjustmentViewSet, basename="payroll-adjustment")
router.register("folha/consignacoes", views.ConsignmentViewSet, basename="payroll-consignment")
router.register("folha/pensoes-alimenticias", views.AlimonyViewSet, basename="payroll-alimony")
router.register("folha/isencoes-ir", views.IrExemptionViewSet, basename="payroll-ir-exemption")
router.register("folha/folhas", views.PayrollRunViewSet, basename="payroll-run")
router.register("folha/contracheques", views.PayslipViewSet, basename="payroll-payslip")
router.register("folha/retroativos", views.RetroactiveViewSet, basename="payroll-retroactive")

urlpatterns = router.urls + [
    path("folha/informe-rendimentos/", views.IncomeReportView.as_view(), name="payroll-income-report"),
]
