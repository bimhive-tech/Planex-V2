"""Report builder: pick progress photos (uploaded in the schedule tab via
progress updates / accepted submissions) for the report's Progress Images
section. All access needs EXPORT_REPORTS (it's part of the report builder)."""
import uuid

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission
from apps.projects.models import ProgressImage

from .models import Report


def _valid_uuids(values):
    """Keep only values that parse as UUIDs — guards the DB filter from junk."""
    out = []
    for v in values or []:
        try:
            out.append(str(uuid.UUID(str(v))))
        except (ValueError, TypeError, AttributeError):
            continue
    return out


class ReportProgressImagesView(APIView):
    """GET the project's progress photos (each with a `selected` flag), earliest
    date first; PUT the chosen IDs to include in the report."""

    permission_classes = [IsAuthenticated]

    def _report(self):
        return get_object_or_404(Report, id=self.kwargs["report_id"], company=self.request.user.company)

    def _require_read(self):
        if Permission.EXPORT_REPORTS not in self.request.user.effective_permissions():
            self.permission_denied(self.request)

    def _require_manage(self):
        if Permission.EXPORT_REPORTS not in self.request.user.effective_permissions():
            self.permission_denied(self.request)

    def get(self, request, report_id):
        self._require_read()
        report = self._report()
        selected = set(str(x) for x in (report.progress_image_ids or []))
        qs = (ProgressImage.objects
              .filter(entry__project=report.project)
              .select_related("entry", "entry__activity")
              .order_by("entry__date", "created_at"))
        data = [{
            "id": str(img.id),
            "url": f"/api/projects/{report.project_id}/progress-images/{img.id}/file/",
            "caption": img.caption,
            "date": img.entry.date.isoformat() if img.entry.date else None,
            "activity_name": img.entry.activity.name if img.entry.activity_id else "",
            "selected": str(img.id) in selected,
        } for img in qs]
        return Response(data)

    def put(self, request, report_id):
        self._require_manage()
        report = self._report()
        ids = request.data.get("selected_ids", [])
        if not isinstance(ids, list):
            raise ValidationError({"selected_ids": "Expected a list of image IDs."})
        # Keep only IDs that really belong to this project's progress photos, in
        # the order the client sent (selection order is cosmetic; the PDF re-sorts
        # by date, but we still persist a clean, valid list).
        valid = set(str(x) for x in ProgressImage.objects
                    .filter(entry__project=report.project, id__in=_valid_uuids(ids))
                    .values_list("id", flat=True))
        report.progress_image_ids = [str(x) for x in ids if str(x) in valid]
        report.save(update_fields=["progress_image_ids", "updated_at"])
        return Response({"selected_ids": report.progress_image_ids})
