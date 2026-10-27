from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("portal-admin/acessos", views.AccessAdminViewSet, basename="portal-access")
router.register("portal-admin/solicitacoes", views.RequestAdminViewSet, basename="portal-request-admin")
router.register("portal-admin/mensagens", views.OutboundMessageViewSet, basename="portal-message")

urlpatterns = router.urls + [
    path("portal/auth/token/", views.PortalLoginView.as_view(), name="portal-login"),
    path("portal/me/", views.MeView.as_view(), name="portal-me"),
    path("portal/beneficios/", views.BenefitsView.as_view(), name="portal-benefits"),
    path("portal/contracheques/", views.PayslipsView.as_view(), name="portal-payslips"),
    path("portal/contracheques/<uuid:pk>/", views.PayslipDetailView.as_view(), name="portal-payslip"),
    path("portal/informe-rendimentos/", views.IncomeReportView.as_view(), name="portal-income"),
    path("portal/processos/", views.ProcessesView.as_view(), name="portal-processes"),
    path("portal/solicitacoes/", views.RequestsView.as_view(), name="portal-requests"),
    path("portal/prova-de-vida/", views.LifeProofView.as_view(), name="portal-life-proof"),
    path("portal/prova-de-vida/<uuid:pk>/enviar/", views.LifeProofSubmitView.as_view(), name="portal-life-proof-submit"),
    path("portal/avisos/", views.NotificationsView.as_view(), name="portal-notifications"),
    path("portal/recadastramento/", views.ReregistrationView.as_view(), name="portal-reregistration"),
    path("portal/recadastramento/<uuid:pk>/enviar/", views.ReregistrationSubmitView.as_view(), name="portal-reregistration-submit"),
]