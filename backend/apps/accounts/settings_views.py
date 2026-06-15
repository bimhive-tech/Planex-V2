"""Settings API: company info, companies, users, roles, permission catalog.
Thin views — tenant scoping via tenancy.resolve_company, logic in settings_services.
"""
from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import settings_services as svc
from .constants import Permission, permission_catalog
from .models import Company, Role, User
from .permissions import HasPermission, IsPlatformAdmin
from .settings_serializers import (
    CompanyCreateSerializer,
    CompanyInfoSerializer,
    CompanyListSerializer,
    RoleSerializer,
    RoleWriteSerializer,
    UserCreateSerializer,
    UserListSerializer,
    UserUpdateSerializer,
)
from .tenancy import resolve_company

ACTIVE_MEMBERS = Q(memberships__is_active=True)


class CompanyInfoView(APIView):
    """GET/PATCH the signed-in user's own company (Settings → Info)."""

    permission_classes = [IsAuthenticated]

    def _own(self, request):
        company = request.user.company
        if company is None:
            raise PermissionDenied("No company context for this user.")
        return Company.objects.annotate(user_count=Count("users", distinct=True)).get(pk=company.pk)

    def get(self, request):
        return Response(CompanyInfoSerializer(self._own(request)).data)

    def patch(self, request):
        if Permission.MANAGE_COMPANY.value not in request.user.effective_permissions():
            raise PermissionDenied("You don't have permission to edit company info.")
        company = self._own(request)
        serializer = CompanyInfoSerializer(company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CompaniesViewSet(viewsets.ViewSet):
    """Platform-admin-only company management (list + create shell)."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def list(self, request):
        qs = Company.objects.annotate(user_count=Count("users", distinct=True)).order_by("name")
        page = StandardListMixin.paginate(self, qs, request)
        return page(CompanyListSerializer)

    def create(self, request):
        serializer = CompanyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = svc.create_company(name=serializer.validated_data["name"])
        company.user_count = 0
        return Response(CompanyListSerializer(company).data, status=status.HTTP_201_CREATED)


class RolesViewSet(viewsets.ViewSet):
    """Roles within the resolved company. Requires MANAGE_ROLES."""

    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = Permission.MANAGE_ROLES.value

    def _company(self, request):
        return resolve_company(request, request.query_params.get("company"))

    def list(self, request):
        company = self._company(request)
        qs = (
            Role.objects.filter(company=company)
            .annotate(member_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .order_by("name")
        )
        page = StandardListMixin.paginate(self, qs, request)
        return page(RoleSerializer)

    def create(self, request):
        company = self._company(request)
        serializer = RoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = svc.create_role(company=company, **serializer.validated_data)
        role.member_count = 0
        return Response(RoleSerializer(role).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company = self._company(request)
        role = self._get_role(company, pk)
        serializer = RoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        svc.update_role(role=role, **serializer.validated_data)
        return Response(RoleSerializer(self._annotated_role(company, role.pk)).data)

    def destroy(self, request, pk=None):
        company = self._company(request)
        role = self._get_role(company, pk)
        if role.memberships.exists():
            raise PermissionDenied("Can't delete a role that is still assigned to users.")
        role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _get_role(self, company, pk):
        from rest_framework.exceptions import NotFound
        try:
            return Role.objects.get(pk=pk, company=company)
        except (Role.DoesNotExist, ValueError):
            raise NotFound("Role not found.")

    def _annotated_role(self, company, pk):
        return (
            Role.objects.filter(company=company)
            .annotate(member_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .get(pk=pk)
        )


class UsersViewSet(viewsets.ViewSet):
    """Users within the resolved company. Requires MANAGE_USERS."""

    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = Permission.MANAGE_USERS.value

    def _company(self, request):
        return resolve_company(request, request.query_params.get("company"))

    def _queryset(self, company, search=None):
        qs = User.objects.filter(company=company).prefetch_related(
            "memberships__role"
        ).select_related("company").order_by("email")
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        return qs

    def list(self, request):
        company = self._company(request)
        qs = self._queryset(company, request.query_params.get("search"))
        page = StandardListMixin.paginate(self, qs, request)
        return page(UserListSerializer)

    def create(self, request):
        company = self._company(request)
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._validate_roles(company, serializer.validated_data["role_ids"])
        user = svc.create_user(company=company, **serializer.validated_data)
        return Response(self._serialized(user), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        company = self._company(request)
        user = self._get_user(company, pk)
        serializer = UserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "role_ids" in serializer.validated_data:
            self._validate_roles(company, serializer.validated_data["role_ids"])
        svc.update_user(user=user, data=serializer.validated_data)
        return Response(self._serialized(self._get_user(company, pk)))

    def _serialized(self, user):
        user = User.objects.filter(pk=user.pk).prefetch_related(
            "memberships__role"
        ).select_related("company").get()
        return UserListSerializer(user).data

    def _get_user(self, company, pk):
        from rest_framework.exceptions import NotFound
        try:
            return User.objects.get(pk=pk, company=company)
        except (User.DoesNotExist, ValueError):
            raise NotFound("User not found.")

    def _validate_roles(self, company, role_ids):
        if not role_ids:
            return
        valid = set(Role.objects.filter(company=company, id__in=role_ids).values_list("id", flat=True))
        if len(valid) != len(set(role_ids)):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"role_ids": "One or more roles are invalid for this company."})


class PermissionCatalogView(APIView):
    """Grouped permission keys the resolved company may grant (Roles UI)."""

    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = Permission.MANAGE_ROLES.value

    def get(self, request):
        company = resolve_company(request, request.query_params.get("company"))
        return Response({"groups": permission_catalog(is_platform=company.is_platform_admin)})


class StandardListMixin:
    """Tiny helper to paginate a ViewSet list with the project paginator."""

    @staticmethod
    def paginate(view, queryset, request):
        from .pagination import StandardPagination
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=view)

        def respond(serializer_class):
            return paginator.get_paginated_response(serializer_class(page, many=True).data)

        return respond
