"""Project image upload/list/delete endpoints for private report assets."""
import mimetypes

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Project, ProjectImage
from .serializers import ProjectImageSerializer, ProjectImageUploadSerializer


class ProjectImageAccessMixin:
    """Tenant-safe project lookup plus explicit read/manage permission checks."""

    permission_classes = [IsAuthenticated]

    def get_project(self):
        return get_object_or_404(Project, id=self.kwargs["project_id"], company=self.request.user.company)

    def check_read_permission(self):
        perms = self.request.user.effective_permissions()
        if Permission.VIEW_PROJECTS not in perms and Permission.MANAGE_PROJECTS not in perms:
            self.permission_denied(self.request)

    def check_manage_permission(self):
        if Permission.MANAGE_PROJECTS not in self.request.user.effective_permissions():
            self.permission_denied(self.request)


class ProjectImageListCreateView(ProjectImageAccessMixin, generics.ListCreateAPIView):
    """List existing images or upload a new private image for a project."""

    parser_classes = [MultiPartParser, FormParser]
    pagination_class = None  # small list — return a plain array, not a page object

    def get_queryset(self):
        self.check_read_permission()
        return ProjectImage.objects.filter(project=self.get_project()).select_related("uploaded_by")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectImageUploadSerializer
        return ProjectImageSerializer

    def create(self, request, *args, **kwargs):
        self.check_manage_permission()
        project = self.get_project()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = serializer.save(company=request.user.company, project=project, uploaded_by=request.user)
        return Response(ProjectImageSerializer(image).data, status=status.HTTP_201_CREATED)


class ProjectImageDetailView(ProjectImageAccessMixin, generics.RetrieveDestroyAPIView):
    """Retrieve metadata or delete a private project image."""

    serializer_class = ProjectImageSerializer

    def get_queryset(self):
        self.check_read_permission()
        return ProjectImage.objects.filter(project=self.get_project())

    def destroy(self, request, *args, **kwargs):
        self.check_manage_permission()
        instance = self.get_object()
        if instance.image:
            instance.image.delete(save=False)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectImageFileView(ProjectImageAccessMixin, APIView):
    """Stream a private image's bytes through an authed, tenant-scoped endpoint.

    Works the same in dev (filesystem) and prod (R2) without exposing a public
    URL — the storage backend reads the object by key on demand."""

    def get(self, request, project_id, pk):
        self.check_read_permission()
        image = get_object_or_404(ProjectImage, pk=pk, project=self.get_project())
        if not image.image:
            raise Http404
        content_type = mimetypes.guess_type(image.image.name)[0] or "application/octet-stream"
        return FileResponse(image.image.open("rb"), content_type=content_type)
