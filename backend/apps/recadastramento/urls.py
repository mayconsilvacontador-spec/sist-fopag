from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("recadastramento/campanhas", views.CampaignViewSet, basename="registration-campaign")
router.register("recadastramento/itens", views.ItemViewSet, basename="reregistration")

urlpatterns = router.urls
