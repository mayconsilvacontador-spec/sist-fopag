from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("concessoes", views.ConcessionViewSet, basename="concession")
router.register("beneficios", views.BenefitViewSet, basename="benefit")
router.register("beneficios-importados", views.LegacyBenefitViewSet, basename="legacy-benefit")
router.register("concessao-modelos", views.TemplateViewSet, basename="document-template")
router.register("concessao-checklist", views.ChecklistTemplateViewSet, basename="checklist-template")

urlpatterns = router.urls
