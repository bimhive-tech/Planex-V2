"""Variations API — the logged baseline-adjustment history for a project.

A SCHEDULE variation moves the project's revised finish date (e.g. an extension
of time after a payment delay); a COST variation records a signed change to the
contract value. Reads need VIEW_VARIATIONS (or MANAGE_VARIATIONS), writes need
MANAGE_VARIATIONS."""
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Project, Variation


class VariationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    impact_days = serializers.SerializerMethodField()

    class Meta:
        model = Variation
        fields = ["id", "kind", "kind_display", "title", "reason", "reference", "date",
                  "previous_finish", "new_finish", "impact_days", "amount", "created_at"]

    def get_impact_days(self, obj):
        """Signed day change for a schedule variation (+ extension, − pull-forward)."""
        if obj.kind == Variation.Kind.SCHEDULE and obj.previous_finish and obj.new_finish:
            return (obj.new_finish - obj.previous_finish).days
        return None


class VariationWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variation
        fields = ["kind", "title", "reason", "reference", "date", "new_finish", "amount"]

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        # A schedule variation is meaningless without the date it moves to.
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


def _effective_finish(project):
    """The project's current finish before a new schedule variation applies."""
    return project.revised_finish or project.planned_finish


def _resync_revised_finish(project):
    """Keep the project's revised finish equal to the latest schedule variation's
    new finish, so adding/editing/deleting one stays consistent. Left untouched
    when there are no schedule variations (don't clobber a manual revised date)."""
    latest = (project.variations.filter(kind=Variation.Kind.SCHEDULE, new_finish__isnull=False)
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
            # Snapshot the finish this schedule variation moves away from (for the log).
            previous = _effective_finish(project) if serializer.validated_data.get("kind") == Variation.Kind.SCHEDULE else None
            variation = serializer.save(company=project.company, project=project,
                                        created_by=request.user, previous_finish=previous)
            if variation.kind == Variation.Kind.SCHEDULE:
                _resync_revised_finish(project)
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
            _resync_revised_finish(project)
        return Response(VariationSerializer(variation).data)

    def delete(self, request, project_id, variation_id):
        project = _project(request, project_id)
        _require_manage(request)
        with transaction.atomic():
            self._get(project, variation_id).delete()
            _resync_revised_finish(project)
        return Response(status=status.HTTP_204_NO_CONTENT)
