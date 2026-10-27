from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")
router.register("roles", views.RoleViewSet, basename="role")

urlpatterns = [
    path("auth/token/", views.LoginView.as_view(), name="auth-login"),
    path("auth/token/refresh/", views.RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="auth-change-password"),
    path("roles/<uuid:pk>/permissions/", views.RolePermissionsView.as_view(), name="role-permissions"),
    path("permissions/matrix/", views.PermissionMatrixView.as_view(), name="permission-matrix"),
    path("users-summary/", views.MembershipSummaryView.as_view(), name="users-summary"),
] + router.urls
