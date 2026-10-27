from django.urls import path

from . import views

urlpatterns = [
    path("reports/", views.ReportListView.as_view(), name="reports"),
    path("reports/<slug:code>/", views.ReportRunView.as_view(), name="report-run"),
    path("reports/<slug:code>/export/", views.ReportExportView.as_view(), name="report-export"),
]
