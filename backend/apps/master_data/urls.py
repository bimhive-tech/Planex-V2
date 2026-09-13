"""Master Data routes, mounted under /api/."""
from rest_framework.routers import SimpleRouter

from .views import (
    CurrenciesViewSet,
    PartiesViewSet,
    ProjectPrioritiesViewSet,
    ProjectTypesViewSet,
)

router = SimpleRouter(trailing_slash=True)
router.register("currencies", CurrenciesViewSet, basename="currencies")
router.register("project-types", ProjectTypesViewSet, basename="project-types")
router.register("project-priorities", ProjectPrioritiesViewSet, basename="project-priorities")
# One roster for every role — the four separate /clients/, /consultants/,
# /contractors/ and /subcontractors/ lists it replaces are gone, not aliased:
# the frontend ships in the same container, so there is no older client to
# keep serving.
router.register("parties", PartiesViewSet, basename="parties")

urlpatterns = router.urls
