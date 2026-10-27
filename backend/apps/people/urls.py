from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("people", views.PersonViewSet, basename="person")
router.register("addresses", views.AddressViewSet, basename="address")
router.register("bank-accounts", views.BankAccountViewSet, basename="bank-account")
router.register("dependencies", views.DependencyViewSet, basename="dependency")
router.register("documents", views.DocumentViewSet, basename="document")
router.register("imports", views.ImportBatchViewSet, basename="import")

urlpatterns = router.urls
