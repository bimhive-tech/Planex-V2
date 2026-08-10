"""Part Scope API — a log of a project's contracted "Part" entries (see
PartScope's docstring). Reads need VIEW_FINANCES; writes need MANAGE_FINANCES,
same gate as the rest of the Finances tab it lives under."""
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import PartScope, Project


class PartScopeSerializer(serializers.ModelSerializer):
    delay_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = PartScope
        fields = [
            "id", "title", "amount", "start_date", "completion_revised",
            "forecast_completion", "notes", "delay_days", "created_at",
        ]


class PartScopeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartScope
        fields = ["title", "amount", "start_date", "completion_revised", "forecast_completion", "notes"]


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require(request, perm):
    if perm not in request.user.effective_permissions():
        raise PermissionDenied("You don't have permission to do that.")


def _require_view(request):
    perms = request.user.effective_permissions()
    if Permission.VIEW_FINANCES.value not in perms and Permission.MANAGE_FINANCES.value not in perms:
        raise PermissionDenied("You don't have permission to view this.")


class PartScopeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        return Response(PartScopeSerializer(project.part_scopes.all(), many=True).data)

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_FINANCES.value)
        serializer = PartScopeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(company=project.company, project=project, created_by=request.user)
        return Response(PartScopeSerializer(entry).data, status=status.HTTP_201_CREATED)


class PartScopeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, project, entry_id):
        try:
            return PartScope.objects.get(pk=entry_id, project=project)
        except (PartScope.DoesNotExist, ValueError, TypeError):
            raise NotFound("Part Scope entry not found.")

    def patch(self, request, project_id, entry_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_FINANCES.value)
        entry = self._get(project, entry_id)
        serializer = PartScopeWriteSerializer(entry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PartScopeSerializer(entry).data)

    def delete(self, request, project_id, entry_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_FINANCES.value)
        self._get(project, entry_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
