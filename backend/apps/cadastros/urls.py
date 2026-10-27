from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("entes", views.EnteViewSet, basename="ente")
router.register("organs", views.OrganViewSet, basename="organ")
router.register("positions", views.PositionViewSet, basename="position")
router.register("workplaces", views.WorkplaceViewSet, basename="workplace")
router.register("banks", views.BankViewSet, basename="bank")
router.register("bank-branches", views.BankBranchViewSet, basename="bank-branch")

urlpatterns = router.urls
