from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("protocol/sectors", views.SectorViewSet, basename="protocol-sector")
router.register("protocol/process-types", views.ProcessTypeViewSet, basename="protocol-process-type")
router.register("protocol/holidays", views.HolidayViewSet, basename="protocol-holiday")
router.register("protocol/processes", views.ProcessViewSet, basename="protocol-process")

urlpatterns = router.urls
