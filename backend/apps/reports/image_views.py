"""Per-report image endpoints (cover, progress photos, attachments).

Reads need VIEW_PROJECTS/EXPORT_REPORTS; writes need EXPORT_REPORTS. Bytes
stream through an authed endpoint so private assets never get a public URL."""
import mimetypes

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Report, ReportImage
from .serializers import ReportImageSerializer, ReportImageUploadSerializer


class ReportImageAccessMixin:
    permission_classes = [IsAuthenticated]

    def get_report(self):
        return get_object_or_404(Report, id=self.kwargs["report_id"], company=self.request.user.company)

    def check_read(self):
        perms = self.request.user.effective_permissions()
        if not ({Permission.VIEW_PROJECTS, Permission.EXPORT_REPORTS} & perms):
            self.permission_denied(self.request)

    def check_manage(self):
        if Permission.EXPORT_REPORTS not in self.request.user.effective_permissions():
            self.permission_denied(self.request)


class ReportImageListCreateView(ReportImageAccessMixin, generics.ListCreateAPIView):
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        self.check_read()
        return ReportImage.objects.filter(report=self.get_report())

    def get_serializer_class(self):
        return ReportImageUploadSerializer if self.request.method == "POST" else ReportImageSerializer

    def create(self, request, *args, **kwargs):
        self.check_manage()
        report = self.get_report()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = serializer.save(company=request.user.company, report=report, uploaded_by=request.user)
        return Response(ReportImageSerializer(image).data, status=status.HTTP_201_CREATED)


class ReportImageDetailView(ReportImageAccessMixin, generics.RetrieveDestroyAPIView):
    serializer_class = ReportImageSerializer

    def get_queryset(self):
        self.check_read()
        return ReportImage.objects.filter(report=self.get_report())

    def destroy(self, request, *args, **kwargs):
        self.check_manage()
        instance = self.get_object()
        if instance.image:
            instance.image.delete(save=False)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReportImageFileView(ReportImageAccessMixin, APIView):
    """Stream a private report image's bytes (filesystem or R2)."""

    def get(self, request, report_id, pk):
        self.check_read()
        image = get_object_or_404(ReportImage, pk=pk, report=self.get_report())
        if not image.image:
            raise Http404
        content_type = mimetypes.guess_type(image.image.name)[0] or "application/octet-stream"
        return FileResponse(image.image.open("rb"), content_type=content_type)
