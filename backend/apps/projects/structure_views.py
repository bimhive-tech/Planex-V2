"""Work-hierarchy API: read the project structure tree, and CRUD scopes/activities.

Routes are nested under a project. Reads need VIEW_PROJECTS; writes need
MANAGE_PROJECTS. Everything is company- and project-scoped (tenant isolation).
"""
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Activity, Project, ProjectScope
from .serializers import (
    ActivitySerializer,
    ActivityWriteSerializer,
    ScopeSerializer,
    ScopeWriteSerializer,
)
from .services import project_overall_progress, scope_progress_map


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require(request, perm):
    perms = request.user.effective_permissions()
    if perm not in perms:
        raise PermissionDenied("You don't have permission to do that.")


def _require_view(request):
    perms = request.user.effective_permissions()
    if Permission.VIEW_PROJECTS.value not in perms and Permission.MANAGE_PROJECTS.value not in perms:
        raise PermissionDenied("You don't have permission to view this.")


def _validate_parent(project, parent):
    if parent and parent.project_id != project.id:
        raise ValidationError({"parent": "Parent scope belongs to another project."})


class ProjectStructureView(APIView):
    """GET the full tree (scopes + activities) plus rolled-up progress."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        scopes = project.scopes.all()
        activities = project.activities.all()
        return Response({
            "overall_progress": project_overall_progress(project),
            "scope_progress": scope_progress_map(project),
            "scopes": ScopeSerializer(scopes, many=True).data,
            "activities": ActivitySerializer(activities, many=True).data,
        })


class ScopeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        serializer = ScopeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _validate_parent(project, serializer.validated_data.get("parent"))
        scope = serializer.save(company=request.user.company, project=project)
        return Response(ScopeSerializer(scope).data, status=status.HTTP_201_CREATED)


class ScopeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, project, scope_id):
        try:
            return ProjectScope.objects.get(pk=scope_id, project=project)
        except (ProjectScope.DoesNotExist, ValueError, TypeError):
            raise NotFound("Scope not found.")

    def patch(self, request, project_id, scope_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        scope = self._get(request, project, scope_id)
        serializer = ScopeWriteSerializer(scope, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _validate_parent(project, serializer.validated_data.get("parent"))
        serializer.save()
        return Response(ScopeSerializer(scope).data)

    def delete(self, request, project_id, scope_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        self._get(request, project, scope_id).delete()  # cascades children + activities
        return Response(status=status.HTTP_204_NO_CONTENT)


def _validate_scope(project, scope):
    if scope and scope.project_id != project.id:
        raise ValidationError({"scope": "Scope belongs to another project."})


class ActivityListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        serializer = ActivityWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _validate_scope(project, serializer.validated_data.get("scope"))
        activity = serializer.save(company=request.user.company, project=project)
        return Response(ActivitySerializer(activity).data, status=status.HTTP_201_CREATED)


class ActivityDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, project, activity_id):
        try:
            return Activity.objects.get(pk=activity_id, project=project)
        except (Activity.DoesNotExist, ValueError, TypeError):
            raise NotFound("Activity not found.")

    def patch(self, request, project_id, activity_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        activity = self._get(project, activity_id)
        serializer = ActivityWriteSerializer(activity, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _validate_scope(project, serializer.validated_data.get("scope"))
        serializer.save()
        return Response(ActivitySerializer(activity).data)

    def delete(self, request, project_id, activity_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        self._get(project, activity_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
