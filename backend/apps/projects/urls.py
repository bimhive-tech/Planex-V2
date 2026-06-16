"""Project routes, mounted under /api/."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from .structure_views import (
    ActivityDetailView,
    ActivityListCreateView,
    ProjectImportView,
    ProjectStructureView,
    ProjectZoneGridView,
    ScopeActivitiesView,
    ScopeDetailView,
    ScopeListCreateView,
)
from .milestone_views import MilestoneDetailView, MilestoneListView
from .team_views import (
    AssignableUsersView,
    ProjectMemberDetailView,
    ProjectMemberListView,
)
from .views import ProjectViewSet

router = SimpleRouter(trailing_slash=True)
router.register("projects", ProjectViewSet, basename="projects")

urlpatterns = [
    # Work-hierarchy routes (nested under a project).
    path("projects/<uuid:project_id>/structure/", ProjectStructureView.as_view(), name="project-structure"),
    path("projects/<uuid:project_id>/zones/<uuid:zone_id>/grid/", ProjectZoneGridView.as_view(), name="project-zone-grid"),
    path("projects/<uuid:project_id>/import/", ProjectImportView.as_view(), name="project-import"),
    path("projects/<uuid:project_id>/members/", ProjectMemberListView.as_view(), name="project-members"),
    path("projects/<uuid:project_id>/members/<uuid:member_id>/", ProjectMemberDetailView.as_view(), name="project-member"),
    path("projects/<uuid:project_id>/assignable-users/", AssignableUsersView.as_view(), name="project-assignable-users"),
    path("projects/<uuid:project_id>/milestones/", MilestoneListView.as_view(), name="project-milestones"),
    path("projects/<uuid:project_id>/milestones/<uuid:milestone_id>/", MilestoneDetailView.as_view(), name="project-milestone"),
    path("projects/<uuid:project_id>/scopes/", ScopeListCreateView.as_view(), name="scope-create"),
    path("projects/<uuid:project_id>/scopes/<uuid:scope_id>/", ScopeDetailView.as_view(), name="scope-detail"),
    path("projects/<uuid:project_id>/scopes/<uuid:scope_id>/activities/", ScopeActivitiesView.as_view(), name="scope-activities"),
    path("projects/<uuid:project_id>/activities/", ActivityListCreateView.as_view(), name="activity-create"),
    path("projects/<uuid:project_id>/activities/<uuid:activity_id>/", ActivityDetailView.as_view(), name="activity-detail"),
    *router.urls,
]
