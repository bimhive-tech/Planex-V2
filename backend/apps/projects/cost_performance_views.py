"""Read-only rollup of the P6 schedule's own cost/schedule-performance columns
(Budgeted Total Cost, Earned Value Cost, Schedule Variance, durations, SPI) —
imported onto every Activity but otherwise never read anywhere; this is the
one place they get surfaced, on the Finances tab. Gated the same as the rest
of Finances."""
from django.db.models import Q, Sum
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Activity, Project


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require_view_finances(request):
    perms = request.user.effective_permissions()
    if Permission.VIEW_FINANCES.value not in perms and Permission.MANAGE_FINANCES.value not in perms:
        raise PermissionDenied("You don't have permission to view finances.")


class ProjectCostPerformanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view_finances(request)
        agg = project.activities.aggregate(
            budgeted=Sum("budgeted_cost"), earned=Sum("earned_value_cost"), variance=Sum("schedule_variance"),
        )
        return Response({
            "currency": project.currency or "",
            "budgeted_total_cost": str(agg["budgeted"]) if agg["budgeted"] is not None else None,
            "earned_value_cost": str(agg["earned"]) if agg["earned"] is not None else None,
            "schedule_variance": str(agg["variance"]) if agg["variance"] is not None else None,
        })


class ActivityScheduleDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = [
            "id", "name", "code", "phase_name",
            "budgeted_cost", "earned_value_cost", "schedule_variance",
            "baseline_duration", "original_duration", "actual_duration", "remaining_duration",
            "schedule_performance_index", "total_float",
        ]


class ProjectActivityScheduleListView(ListAPIView):
    """The full, paginated, per-activity breakdown of every cost/schedule
    column a P6 import carries — one row per activity, searchable by name.
    The "Schedule Cost" sub-tab's detail table."""
    permission_classes = [IsAuthenticated]
    serializer_class = ActivityScheduleDetailSerializer

    def get_queryset(self):
        project = _project(self.request, self.kwargs["project_id"])
        _require_view_finances(self.request)
        qs = project.activities.order_by("sort_order", "name")
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs
