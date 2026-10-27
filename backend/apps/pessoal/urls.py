from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("ativos/vencimentos", views.ScaleViewSet, basename="active-scale")
router.register("ativos/rubricas", views.RubricViewSet, basename="active-rubric")
router.register("ativos/lancamentos", views.EntryViewSet, basename="active-entry")
router.register("ativos/folhas", views.RunViewSet, basename="active-run")
router.register("ativos/ficha-financeira", views.FinancialRecordViewSet, basename="active-financial")

urlpatterns = router.urls
