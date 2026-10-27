from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("employment-links", views.EmploymentLinkViewSet, basename="employment-link")
router.register("functional-events", views.FunctionalEventViewSet, basename="functional-event")

urlpatterns = router.urls
