from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("provadevida/campanhas", views.CampaignViewSet, basename="life-proof-campaign")
router.register("provadevida/provas", views.ProofViewSet, basename="life-proof")

urlpatterns = router.urls
