"""Settings module routes, mounted under /api/."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from .settings_views import (
    CompaniesViewSet,
    CompanyInfoView,
    PermissionCatalogView,
    RolesViewSet,
    UsersViewSet,
)

router = SimpleRouter(trailing_slash=True)
router.register("companies", CompaniesViewSet, basename="companies")
router.register("roles", RolesViewSet, basename="roles")
router.register("users", UsersViewSet, basename="users")

urlpatterns = [
    path("company/", CompanyInfoView.as_view(), name="company-info"),
    path("permissions/", PermissionCatalogView.as_view(), name="permission-catalog"),
    *router.urls,
]
