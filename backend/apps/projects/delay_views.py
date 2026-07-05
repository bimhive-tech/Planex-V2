"""Project delays / obstacles API (the report's «المعوقات» section).
Reads need VIEW_PROJECTS; writes need MANAGE_PROJECTS."""
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import require_project_permission
from .models import Project, ProjectDelay
from .permissions_catalog import ProjectPermission


class DelaySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ProjectDelay
        fields = ["id", "title", "description", "impact_days", "status", "status_display", "date", "sort_order"]


class DelayWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDelay
        fields = ["title", "description", "impact_days", "status", "date", "sort_order"]


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require_areas(project, request):
    """The Areas of Concern module gates both viewing and managing here."""
    require_project_permission(project, request.user, ProjectPermission.AREAS_OF_CONCERN)


class DelayListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_areas(project, request)
        return Response(DelaySerializer(project.delays.all(), many=True).data)

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require_areas(project, request)
        serializer = DelayWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delay = serializer.save(company=project.company, project=project)
        return Response(DelaySerializer(delay).data, status=status.HTTP_201_CREATED)


class DelayDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, project, delay_id):
        try:
            return ProjectDelay.objects.get(pk=delay_id, project=project)
        except (ProjectDelay.DoesNotExist, ValueError, TypeError):
            raise NotFound("Delay not found.")

    def patch(self, request, project_id, delay_id):
        project = _project(request, project_id)
        _require_areas(project, request)
        delay = self._get(project, delay_id)
        serializer = DelayWriteSerializer(delay, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(DelaySerializer(delay).data)

    def delete(self, request, project_id, delay_id):
        project = _project(request, project_id)
        _require_areas(project, request)
        self._get(project, delay_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
