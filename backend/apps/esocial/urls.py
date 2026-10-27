from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("esocial/eventos", views.EventViewSet, basename="esocial-event")
router.register("esocial/transmissao", views.TransmissionView, basename="esocial-transmission")
router.register("esocial/lotes", views.BatchViewSet, basename="esocial-batch")

urlpatterns = router.urls
