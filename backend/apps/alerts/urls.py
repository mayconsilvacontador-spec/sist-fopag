from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("alerts", views.AlertViewSet, basename="alert")

urlpatterns = router.urls
