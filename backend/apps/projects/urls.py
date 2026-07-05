"""Project routes, mounted under /api/."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from .structure_views import (
    ActivityDetailView,
    ActivityListCreateView,
    ProjectImportView,
    ProjectScheduleImportView,
    ProjectSnapshotsView,
    ProjectStructureView,
    ScopeTreeView,
    ProjectZoneGridView,
    ScopeActivitiesView,
    ScopeDetailView,
    ScopeListCreateView,
)
from .milestone_views import MilestoneDetailView, MilestoneListView
from .delay_views import DelayDetailView, DelayListView
from .finance_views import (
    CashFlowView,
    InvoiceDetailView,
    InvoiceImageView,
    InvoiceListView,
)
from .submittal_views import (
    SubmittalDetailView,
    SubmittalFileView,
    SubmittalListView,
)
from .progress_views import (
    ActivityProgressView,
    ProgressEntryDetailView,
    ProgressEntryImagesView,
    ProgressImageDetailView,
    ProgressImageFileView,
    ProgressImagesListView,
)
from .image_views import ProjectImageDetailView, ProjectImageFileView, ProjectImageListCreateView
from .export_views import ProjectP6ExportView, ProjectP6PrepareView, ProjectP6StatusView
from .notification_views import NotificationListView, NotificationReadView
from .search_views import GlobalSearchView
from .submission_views import ProjectSubmissionsView, SubmissionDecisionView
from .team_views import (
    AssignableUsersView,
    MemberScopeAccessView,
    ProjectMemberDetailView,
    ProjectMemberListView,
    ProjectPermissionCatalogView,
    ProjectZonesView,
)
from .views import ProjectViewSet

router = SimpleRouter(trailing_slash=True)
router.register("projects", ProjectViewSet, basename="projects")

urlpatterns = [
    # Work-hierarchy routes (nested under a project).
    path("projects/<uuid:project_id>/structure/", ProjectStructureView.as_view(), name="project-structure"),
    path("projects/<uuid:project_id>/scope-tree/", ScopeTreeView.as_view(), name="project-scope-tree"),
    path("projects/<uuid:project_id>/zones/<uuid:zone_id>/grid/", ProjectZoneGridView.as_view(), name="project-zone-grid"),
    path("projects/<uuid:project_id>/import/", ProjectImportView.as_view(), name="project-import"),
    path("projects/<uuid:project_id>/schedule-import/", ProjectScheduleImportView.as_view(), name="project-schedule-import"),
    path("projects/<uuid:project_id>/snapshots/", ProjectSnapshotsView.as_view(), name="project-snapshots"),
    path("projects/<uuid:project_id>/export/p6/", ProjectP6ExportView.as_view(), name="project-p6-export"),
    path("projects/<uuid:project_id>/export/p6/prepare/", ProjectP6PrepareView.as_view(), name="project-p6-prepare"),
    path("projects/<uuid:project_id>/export/p6/status/", ProjectP6StatusView.as_view(), name="project-p6-status"),
    path("projects/<uuid:project_id>/activities/<uuid:activity_id>/progress/", ActivityProgressView.as_view(), name="activity-progress"),
    path("projects/<uuid:project_id>/progress-entries/<uuid:entry_id>/", ProgressEntryDetailView.as_view(), name="progress-entry"),
    path("projects/<uuid:project_id>/progress-entries/<uuid:entry_id>/images/", ProgressEntryImagesView.as_view(), name="progress-entry-images"),
    path("projects/<uuid:project_id>/progress-images/", ProgressImagesListView.as_view(), name="progress-images"),
    path("projects/<uuid:project_id>/progress-images/<uuid:image_id>/", ProgressImageDetailView.as_view(), name="progress-image"),
    path("projects/<uuid:project_id>/progress-images/<uuid:image_id>/file/", ProgressImageFileView.as_view(), name="progress-image-file"),
    path("projects/<uuid:project_id>/delays/", DelayListView.as_view(), name="project-delays"),
    path("projects/<uuid:project_id>/delays/<uuid:delay_id>/", DelayDetailView.as_view(), name="project-delay"),
    path("projects/<uuid:project_id>/cashflow/", CashFlowView.as_view(), name="project-cashflow"),
    path("projects/<uuid:project_id>/invoices/", InvoiceListView.as_view(), name="project-invoices"),
    path("projects/<uuid:project_id>/invoices/<uuid:invoice_id>/", InvoiceDetailView.as_view(), name="project-invoice"),
    path("projects/<uuid:project_id>/invoices/<uuid:invoice_id>/image/", InvoiceImageView.as_view(), name="project-invoice-image"),
    path("projects/<uuid:project_id>/submittals/", SubmittalListView.as_view(), name="project-submittals"),
    path("projects/<uuid:project_id>/submittals/<uuid:submittal_id>/", SubmittalDetailView.as_view(), name="project-submittal"),
    path("projects/<uuid:project_id>/submittals/<uuid:submittal_id>/file/", SubmittalFileView.as_view(), name="project-submittal-file"),
    path("projects/<uuid:project_id>/images/", ProjectImageListCreateView.as_view(), name="project-images"),
    path("projects/<uuid:project_id>/images/<uuid:pk>/", ProjectImageDetailView.as_view(), name="project-image"),
    path("projects/<uuid:project_id>/images/<uuid:pk>/file/", ProjectImageFileView.as_view(), name="project-image-file"),
    path("project-permissions/catalog/", ProjectPermissionCatalogView.as_view(), name="project-permission-catalog"),
    path("projects/<uuid:project_id>/members/", ProjectMemberListView.as_view(), name="project-members"),
    path("projects/<uuid:project_id>/members/<uuid:member_id>/", ProjectMemberDetailView.as_view(), name="project-member"),
    path("projects/<uuid:project_id>/assignable-users/", AssignableUsersView.as_view(), name="project-assignable-users"),
    path("projects/<uuid:project_id>/project-zones/", ProjectZonesView.as_view(), name="project-zones-list"),
    path("projects/<uuid:project_id>/members/<uuid:member_id>/scope-access/", MemberScopeAccessView.as_view(), name="member-scope-access"),
    path("search/", GlobalSearchView.as_view(), name="global-search"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/read/", NotificationReadView.as_view(), name="notifications-read"),
    path("projects/<uuid:project_id>/submissions/", ProjectSubmissionsView.as_view(), name="project-submissions"),
    path("projects/<uuid:project_id>/submissions/<uuid:submission_id>/review/",
         SubmissionDecisionView.as_view(stage="review"), name="submission-review"),
    path("projects/<uuid:project_id>/submissions/<uuid:submission_id>/approve/",
         SubmissionDecisionView.as_view(stage="approve"), name="submission-approve"),
    path("projects/<uuid:project_id>/milestones/", MilestoneListView.as_view(), name="project-milestones"),
    path("projects/<uuid:project_id>/milestones/<uuid:milestone_id>/", MilestoneDetailView.as_view(), name="project-milestone"),
    path("projects/<uuid:project_id>/scopes/", ScopeListCreateView.as_view(), name="scope-create"),
    path("projects/<uuid:project_id>/scopes/<uuid:scope_id>/", ScopeDetailView.as_view(), name="scope-detail"),
    path("projects/<uuid:project_id>/scopes/<uuid:scope_id>/activities/", ScopeActivitiesView.as_view(), name="scope-activities"),
    path("projects/<uuid:project_id>/activities/", ActivityListCreateView.as_view(), name="activity-create"),
    path("projects/<uuid:project_id>/activities/<uuid:activity_id>/", ActivityDetailView.as_view(), name="activity-detail"),
    *router.urls,
]
