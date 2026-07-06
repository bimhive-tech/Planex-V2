"""Variations API — Variation Orders against the project baseline.

A SCHEDULE variation (SVO) proposes a new finish date; a COST variation (CVO)
proposes a contract-value change. Each is auto-numbered per project per kind and
moves Pending → Approved / Rejected. The effect (finish date / contract value)
applies ONLY once approved. Reads need VIEW_VARIATIONS (or MANAGE_VARIATIONS),
writes/decisions need MANAGE_VARIATIONS."""
import re

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Project, Variation


class VariationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default="")
    impact_days = serializers.SerializerMethodField()

    class Meta:
        model = Variation
        fields = ["id", "kind", "kind_display", "number", "title", "reason", "date",
                  "status", "status_display", "decided_at", "decided_by_name",
                  "previous_finish", "new_finish", "impact_days", "amount", "created_at"]

    def get_impact_days(self, obj):
        """Signed day change for an approved schedule VO (+ extension, − pull-forward)."""
        if obj.kind == Variation.Kind.SCHEDULE and obj.previous_finish and obj.new_finish:
            return (obj.new_finish - obj.previous_finish).days
        return None


class VariationWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variation
        fields = ["kind", "title", "reason", "date", "new_finish", "amount"]

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        new_finish = attrs.get("new_finish", getattr(self.instance, "new_finish", None))
        if kind == Variation.Kind.SCHEDULE and self.instance is None and not new_finish:
            raise serializers.ValidationError({"new_finish": "A schedule variation needs a new finish date."})
        return attrs


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require_view(request):
    perms = request.user.effective_permissions()
    if Permission.VIEW_VARIATIONS.value not in perms and Permission.MANAGE_VARIATIONS.value not in perms:
        raise PermissionDenied("You don't have permission to view variations.")


def _require_manage(request):
    if Permission.MANAGE_VARIATIONS.value not in request.user.effective_permissions():
        raise PermissionDenied("You don't have permission to manage variations.")


def _next_number(project, kind):
    """Next VO number for this project + kind, e.g. 'SVO-003'. Derived from the
    highest existing suffix so deletes don't cause a collision."""
    prefix = Variation.NUMBER_PREFIX[kind]
    highest = 0
    for num in project.variations.filter(kind=kind).values_list("number", flat=True):
        m = re.search(r"(\d+)$", num or "")
        if m:
            highest = max(highest, int(m.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def _effective_finish(project):
    """The project's current finish before a schedule VO applies."""
    return project.revised_finish or project.planned_finish


def _resync_revised_finish(project):
    """Keep the project's revised finish equal to the latest APPROVED schedule VO's
    new finish. Only approved variations count — a pending/rejected one has no
    effect. Left untouched when there are no approved schedule VOs."""
    latest = (project.variations
              .filter(kind=Variation.Kind.SCHEDULE, status=Variation.Status.APPROVED, new_finish__isnull=False)
              .order_by("-date", "-created_at").first())
    if latest and project.revised_finish != latest.new_finish:
        project.revised_finish = latest.new_finish
        project.save(update_fields=["revised_finish", "updated_at"])


class VariationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        qs = project.variations.all()
        kind = request.query_params.get("kind")
        if kind in (Variation.Kind.SCHEDULE, Variation.Kind.COST):
            qs = qs.filter(kind=kind)
        return Response(VariationSerializer(qs, many=True).data)

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require_manage(request)
        serializer = VariationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            variation = serializer.save(
                company=project.company, project=project, created_by=request.user,
                status=Variation.Status.PENDING,
                number=_next_number(project, serializer.validated_data["kind"]))
        return Response(VariationSerializer(variation).data, status=status.HTTP_201_CREATED)


class VariationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, project, variation_id):
        try:
            return Variation.objects.get(pk=variation_id, project=project)
        except (Variation.DoesNotExist, ValueError, TypeError):
            raise NotFound("Variation not found.")

    def patch(self, request, project_id, variation_id):
        project = _project(request, project_id)
        _require_manage(request)
        variation = self._get(project, variation_id)
        serializer = VariationWriteSerializer(variation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
            _resync_revised_finish(project)  # an edited, already-approved SVO may shift it
        return Response(VariationSerializer(variation).data)

    def delete(self, request, project_id, variation_id):
        project = _project(request, project_id)
        _require_manage(request)
        with transaction.atomic():
            self._get(project, variation_id).delete()
            _resync_revised_finish(project)
        return Response(status=status.HTTP_204_NO_CONTENT)


class VariationDecisionView(APIView):
    """Approve or reject a pending variation, stamping who decided and when. Only
    on approval does a schedule VO move the finish / a cost VO count toward the
    contract value."""

    permission_classes = [IsAuthenticated]

    def post(self, request, project_id, variation_id):
        project = _project(request, project_id)
        _require_manage(request)
        try:
            variation = Variation.objects.get(pk=variation_id, project=project)
        except (Variation.DoesNotExist, ValueError, TypeError):
            raise NotFound("Variation not found.")

        decision = request.data.get("decision")
        if decision not in ("approve", "reject"):
            raise ValidationError({"decision": "Must be 'approve' or 'reject'."})

        with transaction.atomic():
            if decision == "approve":
                variation.status = Variation.Status.APPROVED
                # Snapshot the finish this VO replaces, at the moment it takes effect.
                if variation.kind == Variation.Kind.SCHEDULE:
                    variation.previous_finish = _effective_finish(project)
            else:
                variation.status = Variation.Status.REJECTED
            variation.decided_at = timezone.now()
            variation.decided_by = request.user
            variation.save(update_fields=["status", "previous_finish", "decided_at", "decided_by", "updated_at"])
            _resync_revised_finish(project)
        return Response(VariationSerializer(variation).data)
