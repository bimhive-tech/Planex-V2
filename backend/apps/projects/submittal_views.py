"""Project submittals API (shop drawings / materials and their approval status).
Reads need VIEW_SUBMITTALS (or MANAGE_SUBMITTALS), writes need MANAGE_SUBMITTALS."""
import mimetypes

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Project, Submittal


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require_view_submittals(request):
    perms = request.user.effective_permissions()
    if Permission.VIEW_SUBMITTALS.value not in perms and Permission.MANAGE_SUBMITTALS.value not in perms:
        raise PermissionDenied("You don't have permission to view submittals.")


def _require_manage_submittals(request):
    if Permission.MANAGE_SUBMITTALS.value not in request.user.effective_permissions():
        raise PermissionDenied("You don't have permission to manage submittals.")


class SubmittalSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_submittal_type_display", read_only=True)
    discipline_display = serializers.CharField(source="get_discipline_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    has_attachment = serializers.SerializerMethodField()

    class Meta:
        model = Submittal
        fields = ["id", "title", "submittal_type", "type_display", "discipline", "discipline_display",
                  "status", "status_display", "reference", "date", "sort_order", "has_attachment"]

    def get_has_attachment(self, obj):
        return bool(obj.attachment)


class SubmittalWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submittal
        fields = ["title", "submittal_type", "discipline", "status", "reference", "date", "attachment", "sort_order"]


class SubmittalListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view_submittals(request)
        return Response(SubmittalSerializer(project.submittals.all(), many=True).data)

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require_manage_submittals(request)
        serializer = SubmittalWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submittal = serializer.save(company=project.company, project=project, created_by=request.user)
        return Response(SubmittalSerializer(submittal).data, status=status.HTTP_201_CREATED)


class SubmittalDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _get(self, project, submittal_id):
        try:
            return Submittal.objects.get(pk=submittal_id, project=project)
        except (Submittal.DoesNotExist, ValueError, TypeError):
            raise NotFound("Submittal not found.")

    def patch(self, request, project_id, submittal_id):
        project = _project(request, project_id)
        _require_manage_submittals(request)
        submittal = self._get(project, submittal_id)
        serializer = SubmittalWriteSerializer(submittal, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(SubmittalSerializer(submittal).data)

    def delete(self, request, project_id, submittal_id):
        project = _project(request, project_id)
        _require_manage_submittals(request)
        submittal = self._get(project, submittal_id)
        if submittal.attachment:
            submittal.attachment.delete(save=False)
        submittal.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubmittalFileView(APIView):
    """Stream a submittal attachment (drawing/PDF/image) through an authed,
    tenant-scoped endpoint — no public URL, same on local disk and R2."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, submittal_id):
        project = _project(request, project_id)
        _require_view_submittals(request)
        submittal = get_object_or_404(Submittal, pk=submittal_id, project=project)
        if not submittal.attachment:
            raise Http404
        content_type = mimetypes.guess_type(submittal.attachment.name)[0] or "application/octet-stream"
        return FileResponse(submittal.attachment.open("rb"), content_type=content_type)
