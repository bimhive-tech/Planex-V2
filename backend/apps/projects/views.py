"""Projects API. Company-scoped CRUD for the Project Hub + detail.

Access: VIEW_PROJECTS to read, MANAGE_PROJECTS to create/edit/archive/delete.
"""
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.accounts.constants import Permission

from .models import Project
from .serializers import (
    ProjectDetailSerializer,
    ProjectListSerializer,
    ProjectWriteSerializer,
)

READ_ACTIONS = {"list", "retrieve"}


class ProjectAccess(BasePermission):
    """VIEW_PROJECTS for reads; MANAGE_PROJECTS for writes."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        perms = user.effective_permissions()
        if view.action in READ_ACTIONS:
            return Permission.VIEW_PROJECTS in perms or Permission.MANAGE_PROJECTS in perms
        return Permission.MANAGE_PROJECTS in perms


class ProjectViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ProjectAccess]
    lookup_field = "pk"

    def get_queryset(self):
        # Tenant isolation: only the caller's own company's projects.
        qs = Project.objects.filter(company=self.request.user.company)

        # Search/type/archive filters apply to the list only — detail, update, and
        # delete must still reach archived projects.
        if self.action != "list":
            return qs

        params = self.request.query_params
        status_filter = params.get("status", "active")
        if status_filter == "active":
            qs = qs.filter(is_archived=False)
        elif status_filter == "archived":
            qs = qs.filter(is_archived=True)
        # "all" → no archive filter

        project_type = params.get("type")
        if project_type:
            qs = qs.filter(project_type=project_type)

        search = params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(location__icontains=search)
                           | Q(client_name__icontains=search))
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return ProjectListSerializer
        if self.action in {"create", "update", "partial_update"}:
            return ProjectWriteSerializer
        return ProjectDetailSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["company"] = self.request.user.company
        return ctx

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    def create(self, request, *args, **kwargs):
        # Return the full detail representation after a write (not the write shape).
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        self.perform_create(write)
        from rest_framework.response import Response
        from rest_framework import status
        return Response(ProjectDetailSerializer(write.instance).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        write = self.get_serializer(instance, data=request.data, partial=partial)
        write.is_valid(raise_exception=True)
        write.save()
        from rest_framework.response import Response
        return Response(ProjectDetailSerializer(write.instance).data)
