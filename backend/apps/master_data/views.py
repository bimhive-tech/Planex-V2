"""Master Data API: currencies, project types, project priorities and the
party roster. Thin views — tenant scoping via accounts.tenancy.resolve_company,
logic in services.py. Writing any of them requires MANAGE_MASTER_DATA."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.constants import Permission
from apps.accounts.permissions import HasPermission
from apps.accounts.settings_views import StandardListMixin
from apps.accounts.tenancy import resolve_company

from . import services as svc
from .models import Currency, Party, ProjectPriority, ProjectType
from .serializers import (
    CurrencyCreateSerializer,
    CurrencySerializer,
    CurrencyUpdateSerializer,
    NameOnlySerializer,
    PartySerializer,
    PartyWriteSerializer,
    ProjectPrioritySerializer,
    ProjectTypeSerializer,
)


class _MasterDataViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, HasPermission]

    @property
    def required_permission(self):
        """Curating a list is an Administration job; READING one is not.

        These lists exist to populate the project form's dropdowns, so gating
        reads on MANAGE_MASTER_DATA left anyone who can create a project but
        isn't a company admin — the common case — staring at dropdowns stuck on
        "Loading…", their own project's type and currency included. Reading
        discloses nothing new either: every value here is already visible on
        the projects themselves to the same VIEW_PROJECTS holders. Writes stay
        on MANAGE_MASTER_DATA.
        """
        if self.action == "list":
            return Permission.VIEW_PROJECTS.value
        return Permission.MANAGE_MASTER_DATA.value

    def _company(self, request):
        return resolve_company(request, request.query_params.get("company"))


class CurrenciesViewSet(_MasterDataViewSet):
    def list(self, request):
        company = self._company(request)
        qs = Currency.objects.filter(company=company)
        page = StandardListMixin.paginate(self, qs, request)
        return page(CurrencySerializer)

    def create(self, request):
        company = self._company(request)
        serializer = CurrencyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            currency = svc.create_currency(company=company, **serializer.validated_data)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(CurrencySerializer(currency).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company = self._company(request)
        currency = self._get(company, pk)
        serializer = CurrencyUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            svc.update_currency(currency=currency, **serializer.validated_data)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(CurrencySerializer(self._get(company, pk)).data)

    def destroy(self, request, pk=None):
        company = self._company(request)
        currency = self._get(company, pk)
        try:
            svc.delete_currency(currency=currency)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        """The only way is_default changes — a plain field edit can't flip it
        without also un-defaulting every other currency in the company."""
        company = self._company(request)
        currency = self._get(company, pk)
        svc.set_default_currency(currency=currency)
        return Response(CurrencySerializer(self._get(company, pk)).data)

    def _get(self, company, pk):
        try:
            return Currency.objects.get(pk=pk, company=company)
        except (Currency.DoesNotExist, ValueError):
            raise NotFound("Currency not found.")


class ProjectTypesViewSet(_MasterDataViewSet):
    def list(self, request):
        company = self._company(request)
        qs = ProjectType.objects.filter(company=company)
        page = StandardListMixin.paginate(self, qs, request)
        return page(ProjectTypeSerializer)

    def create(self, request):
        company = self._company(request)
        serializer = NameOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = svc.create_project_type(company=company, **serializer.validated_data)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(ProjectTypeSerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company = self._company(request)
        item = self._get(company, pk)
        serializer = NameOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            svc.update_project_type(project_type=item, **serializer.validated_data)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(ProjectTypeSerializer(self._get(company, pk)).data)

    def destroy(self, request, pk=None):
        company = self._company(request)
        item = self._get(company, pk)
        try:
            svc.delete_project_type(project_type=item)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _get(self, company, pk):
        try:
            return ProjectType.objects.get(pk=pk, company=company)
        except (ProjectType.DoesNotExist, ValueError):
            raise NotFound("Project type not found.")


class ProjectPrioritiesViewSet(_MasterDataViewSet):
    def list(self, request):
        company = self._company(request)
        qs = ProjectPriority.objects.filter(company=company)
        page = StandardListMixin.paginate(self, qs, request)
        return page(ProjectPrioritySerializer)

    def create(self, request):
        company = self._company(request)
        serializer = NameOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = svc.create_project_priority(company=company, **serializer.validated_data)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(ProjectPrioritySerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company = self._company(request)
        item = self._get(company, pk)
        serializer = NameOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            svc.update_project_priority(priority=item, **serializer.validated_data)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(ProjectPrioritySerializer(self._get(company, pk)).data)

    def destroy(self, request, pk=None):
        company = self._company(request)
        item = self._get(company, pk)
        try:
            svc.delete_project_priority(priority=item)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _get(self, company, pk):
        try:
            return ProjectPriority.objects.get(pk=pk, company=company)
        except (ProjectPriority.DoesNotExist, ValueError):
            raise NotFound("Project priority not found.")


class PartiesViewSet(_MasterDataViewSet):
    """CRUD for the company's one party roster — the firms a project can name
    as its owner, consultant, contractor or sub-contractor. There is no role
    here: a project decides what a party is to it by naming it in that role's
    field, so the same firm serves every dropdown."""

    def list(self, request):
        company = self._company(request)
        qs = Party.objects.filter(company=company)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        page = StandardListMixin.paginate(self, qs, request)
        return page(PartySerializer)

    def create(self, request):
        company = self._company(request)
        serializer = PartyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = svc.create_party(company=company, **serializer.validated_data)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(PartySerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company = self._company(request)
        item = self._get(company, pk)
        serializer = PartyWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            svc.update_party(instance=item, **serializer.validated_data)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(PartySerializer(self._get(company, pk)).data)

    def destroy(self, request, pk=None):
        company = self._company(request)
        item = self._get(company, pk)
        try:
            svc.delete_party(instance=item)
        except svc.MasterDataError as exc:
            raise ValidationError(str(exc))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _get(self, company, pk):
        try:
            return Party.objects.get(pk=pk, company=company)
        except (Party.DoesNotExist, ValueError):
            raise NotFound("Party not found.")
