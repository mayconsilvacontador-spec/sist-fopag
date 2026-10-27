from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("actuarial-bases", views.ActuarialBaseViewSet, basename="actuarial-base")

urlpatterns = router.urls
