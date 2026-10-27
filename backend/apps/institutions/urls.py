from django.urls import path
from rest_framework.routers import DefaultRouter

from . import branding, views

router = DefaultRouter()
router.register("plans", views.BenefitPlanViewSet, basename="plan")
router.register("payroll-groups", views.PayrollGroupViewSet, basename="payroll-group")
router.register("life-purchases", views.LifePurchaseViewSet, basename="life-purchase")
router.register("fiscal-years", views.FiscalYearViewSet, basename="fiscal-year")
router.register("competences", views.CompetenceViewSet, basename="competence")
router.register("parameters", views.ParameterViewSet, basename="parameter")

urlpatterns = [
    path("institution/current/", views.CurrentInstitutionView.as_view(), name="institution-current"),
    path("institution/current/branding/<str:kind>/", branding.BrandingUploadView.as_view(), name="institution-branding"),
    path("branding/", branding.PublicBrandingView.as_view(), name="branding"),
    path("branding/<str:kind>/", branding.PublicBrandingImageView.as_view(), name="branding-image"),
    path("institution/current/life-purchase/", views.LifePurchaseToggleView.as_view(),
         name="institution-life-purchase"),
] + router.urls
