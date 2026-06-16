"""Reports routes, mounted under /api/."""
from rest_framework.routers import SimpleRouter

from .views import ReportTemplateViewSet, ReportViewSet

router = SimpleRouter(trailing_slash=True)
router.register("report-templates", ReportTemplateViewSet, basename="report-templates")
router.register("reports", ReportViewSet, basename="reports")

urlpatterns = router.urls
