"""Project milestones API. Reads need VIEW_PROJECTS; writes need MANAGE_PROJECTS."""
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Milestone, Project


class MilestoneSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    scope_id = serializers.SerializerMethodField()
    # Ancestor chain top-down (e.g. ["PH1", "Z(A)", "Building 15"]) for
    # grouping the full Milestones list by zone/building — null for
    # project-wide milestones and any manually added one.
    scope_path = serializers.SerializerMethodField()

    class Meta:
        model = Milestone
        fields = [
            "id", "title", "date", "status", "status_display", "sort_order",
            "progress_percent", "scope_id", "scope_path",
        ]

    def get_scope_id(self, obj):
        return str(obj.scope_id) if obj.scope_id else None

    def get_scope_path(self, obj):
        if not obj.scope_id:
            return None
        names, node = [], obj.scope
        while node:
            names.append(node.label or node.name)
            node = node.parent
        return list(reversed(names))


class MilestoneWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = ["title", "date", "status", "sort_order"]


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
    if Permission.VIEW_PROJECTS.value not in perms and Permission.MANAGE_PROJECTS.value not in perms:
        raise PermissionDenied("You don't have permission to view this.")


class MilestoneListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        # scope's own ancestor chain tops out at 4 levels (Stage>Zone>Area>Phase)
        # — select_related that far so scope_path never re-queries per row.
        milestones = project.milestones.select_related("scope__parent__parent__parent")
        return Response(MilestoneSerializer(milestones, many=True).data)

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        serializer = MilestoneWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        milestone = serializer.save(company=project.company, project=project)
        return Response(MilestoneSerializer(milestone).data, status=status.HTTP_201_CREATED)


class MilestoneDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, project, milestone_id):
        try:
            return Milestone.objects.get(pk=milestone_id, project=project)
        except (Milestone.DoesNotExist, ValueError, TypeError):
            raise NotFound("Milestone not found.")

    def patch(self, request, project_id, milestone_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        milestone = self._get(project, milestone_id)
        serializer = MilestoneWriteSerializer(milestone, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MilestoneSerializer(milestone).data)

    def delete(self, request, project_id, milestone_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        self._get(project, milestone_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
