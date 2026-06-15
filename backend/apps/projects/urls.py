"""Project routes, mounted under /api/."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from .structure_views import (
    ActivityDetailView,
    ActivityListCreateView,
    ProjectImportView,
    ProjectStructureView,
    ScopeDetailView,
    ScopeListCreateView,
)
from .views import ProjectViewSet

router = SimpleRouter(trailing_slash=True)
router.register("projects", ProjectViewSet, basename="projects")

urlpatterns = [
    # Work-hierarchy routes (nested under a project).
    path("projects/<uuid:project_id>/structure/", ProjectStructureView.as_view(), name="project-structure"),
    path("projects/<uuid:project_id>/import/", ProjectImportView.as_view(), name="project-import"),
    path("projects/<uuid:project_id>/scopes/", ScopeListCreateView.as_view(), name="scope-create"),
    path("projects/<uuid:project_id>/scopes/<uuid:scope_id>/", ScopeDetailView.as_view(), name="scope-detail"),
    path("projects/<uuid:project_id>/activities/", ActivityListCreateView.as_view(), name="activity-create"),
    path("projects/<uuid:project_id>/activities/<uuid:activity_id>/", ActivityDetailView.as_view(), name="activity-detail"),
    *router.urls,
]
