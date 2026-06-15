"""Project routes, mounted under /api/."""
from rest_framework.routers import SimpleRouter

from .views import ProjectViewSet

router = SimpleRouter(trailing_slash=True)
router.register("projects", ProjectViewSet, basename="projects")

urlpatterns = [*router.urls]
