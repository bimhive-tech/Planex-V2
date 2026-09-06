"""Master Data routes, mounted under /api/."""
from rest_framework.routers import SimpleRouter

from .views import (
    ClientsViewSet,
    ConsultantsViewSet,
    ContractorsViewSet,
    CurrenciesViewSet,
    ProjectPrioritiesViewSet,
    ProjectTypesViewSet,
    SubContractorsViewSet,
)

router = SimpleRouter(trailing_slash=True)
router.register("currencies", CurrenciesViewSet, basename="currencies")
router.register("project-types", ProjectTypesViewSet, basename="project-types")
router.register("project-priorities", ProjectPrioritiesViewSet, basename="project-priorities")
router.register("clients", ClientsViewSet, basename="clients")
router.register("consultants", ConsultantsViewSet, basename="consultants")
router.register("contractors", ContractorsViewSet, basename="contractors")
router.register("subcontractors", SubContractorsViewSet, basename="subcontractors")

urlpatterns = router.urls
