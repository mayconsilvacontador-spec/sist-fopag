from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("leitura/leituras", views.JobViewSet, basename="reading-job")

urlpatterns = router.urls + [
    path("leitura/configuracao/", views.SettingsView.as_view()),
    path("leitura/configuracao/testar/", views.SettingsTestView.as_view()),
]
