"""Master Data routes, mounted under /api/."""
from rest_framework.routers import SimpleRouter

from .views import CurrenciesViewSet, ProjectPrioritiesViewSet, ProjectTypesViewSet

router = SimpleRouter(trailing_slash=True)
router.register("currencies", CurrenciesViewSet, basename="currencies")
router.register("project-types", ProjectTypesViewSet, basename="project-types")
router.register("project-priorities", ProjectPrioritiesViewSet, basename="project-priorities")

urlpatterns = router.urls
