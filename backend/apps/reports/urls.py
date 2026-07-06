"""Reports routes, mounted under /api/."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from .image_views import (
    ReportImageDetailView,
    ReportImageFileView,
    ReportImageListCreateView,
)
from .progress_image_views import ReportProgressImagesView
from .views import ReportTemplateViewSet, ReportViewSet

router = SimpleRouter(trailing_slash=True)
router.register("report-templates", ReportTemplateViewSet, basename="report-templates")
router.register("reports", ReportViewSet, basename="reports")

urlpatterns = [
    path("reports/<uuid:report_id>/images/", ReportImageListCreateView.as_view(), name="report-images"),
    path("reports/<uuid:report_id>/images/<uuid:pk>/", ReportImageDetailView.as_view(), name="report-image"),
    path("reports/<uuid:report_id>/images/<uuid:pk>/file/", ReportImageFileView.as_view(), name="report-image-file"),
    path("reports/<uuid:report_id>/progress-images/", ReportProgressImagesView.as_view(), name="report-progress-images"),
    *router.urls,
]
