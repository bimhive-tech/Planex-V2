"""Progress submission + approval-chain API.

Flow: a field user with SUBMIT_PROGRESS submits a value (Pending Review); a user
with REVIEW_PROGRESS approves it to Pending PM Approval (or rejects); a user with
APPROVE_PROGRESS gives final acceptance (which updates the activity's official
progress) or rejects. Rejected submissions stay in history; the user resubmits a
new one. Everything is permission-gated, not role-gated.
"""
import mimetypes

from django.conf import settings
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .access import accessible_scope_ids
from .models import Activity, ProgressEntry, ProgressImage, ProgressSubmission, Project, SubmissionImage
from .notifications import notify_decision, notify_submitted

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class SubmissionImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = SubmissionImage
        fields = ["id", "url", "caption", "created_at"]

    def get_url(self, obj):
        return f"/api/projects/{obj.submission.project_id}/submissions/{obj.submission_id}/images/{obj.id}/file/"


class SubmissionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    activity_name = serializers.CharField(source="activity.name", read_only=True)
    activity_path = serializers.SerializerMethodField()
    submitted_by_name = serializers.CharField(source="submitted_by.full_name", default="", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", default="", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.full_name", default="", read_only=True)
    images = SubmissionImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProgressSubmission
        fields = [
            "id", "activity", "activity_name", "activity_path",
            "previous_progress", "submitted_progress", "status", "status_display",
            "note", "review_comment", "submitted_by_name", "reviewed_by_name",
            "approved_by_name", "images", "reviewed_at", "decided_at", "created_at", "updated_at",
        ]

    def get_activity_path(self, obj):
        # activity.scope = phase -> subzone -> zone (select_related'd in the view).
        phase = obj.activity.scope
        parts = []
        node = phase
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return " / ".join(reversed(parts))


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


_SUBMISSIONS_QS = "activity__scope__parent__parent", "submitted_by", "reviewed_by", "approved_by"


class ProjectSubmissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        qs = project.submissions.select_related(*_SUBMISSIONS_QS).prefetch_related("images")
        status_filter = request.query_params.get("status")
        if status_filter == "open":
            qs = qs.filter(status__in=ProgressSubmission.OPEN_STATES)
        elif status_filter:
            qs = qs.filter(status=status_filter)
        return Response(SubmissionSerializer(qs[:200], many=True).data)

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.SUBMIT_PROGRESS.value)
        activity_id = request.data.get("activity")
        try:
            activity = Activity.objects.get(pk=activity_id, project=project)
        except (Activity.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"activity": "Activity not found."})
        accessible = accessible_scope_ids(project, request.user)
        if accessible is not None and activity.scope_id not in accessible:
            raise PermissionDenied("You can't submit progress for this part of the project.")
        try:
            value = round(float(request.data.get("submitted_progress")), 2)
        except (TypeError, ValueError):
            raise ValidationError({"submitted_progress": "A number is required."})
        if value < 0 or value > 100:
            raise ValidationError({"submitted_progress": "Progress must be 0–100."})

        sub = ProgressSubmission.objects.create(
            company=project.company, project=project, activity=activity,
            submitted_by=request.user, previous_progress=activity.progress_percent,
            submitted_progress=value, note=request.data.get("note", ""),
        )
        sub = ProgressSubmission.objects.select_related(*_SUBMISSIONS_QS).get(pk=sub.pk)
        notify_submitted(sub)
        return Response(SubmissionSerializer(sub).data, status=status.HTTP_201_CREATED)


def _record_accepted_entry(sub):
    """On final acceptance, write a dated ProgressEntry (so the accepted value
    shows up in the activity's history) and copy the submission's evidence
    photos onto it (so they appear in the zone's photo-history gallery, which
    only reads ProgressImage — SubmissionImage stays too, as the approval
    audit trail on the submission card itself)."""
    entry = ProgressEntry.objects.create(
        company=sub.company, project=sub.project, activity=sub.activity,
        date=timezone.now().date(), progress_percent=sub.submitted_progress,
        note=sub.note, recorded_by=sub.submitted_by,
    )
    for simg in sub.images.all():
        pimg = ProgressImage(company=sub.company, entry=entry, caption=simg.caption, uploaded_by=simg.uploaded_by)
        name = simg.image.name.rsplit("/", 1)[-1]
        pimg.image.save(name, ContentFile(simg.image.read()), save=True)


class SubmissionDecisionView(APIView):
    """POST a review or PM decision (approve/reject) on a submission."""

    permission_classes = [IsAuthenticated]
    stage = None  # "review" or "approve" — set by the URL conf

    def post(self, request, project_id, submission_id):
        project = _project(request, project_id)
        try:
            sub = ProgressSubmission.objects.select_related(*_SUBMISSIONS_QS).get(pk=submission_id, project=project)
        except (ProgressSubmission.DoesNotExist, ValueError, TypeError):
            raise NotFound("Submission not found.")

        decision = request.data.get("decision")
        comment = request.data.get("comment", "")
        if decision not in ("approve", "reject"):
            raise ValidationError({"decision": "Must be 'approve' or 'reject'."})
        if decision == "reject" and not comment.strip():
            raise ValidationError({"comment": "A comment is required when rejecting."})

        S = ProgressSubmission.Status
        if self.stage == "review":
            _require(request, Permission.REVIEW_PROGRESS.value)
            if sub.status != S.PENDING_REVIEW:
                raise ValidationError({"status": "This submission isn't awaiting review."})
            sub.reviewed_by = request.user
            sub.review_comment = comment
            sub.reviewed_at = timezone.now()
            sub.status = S.PENDING_PM if decision == "approve" else S.REVIEWER_REJECTED
            sub.save(update_fields=["reviewed_by", "review_comment", "reviewed_at", "status", "updated_at"])
        else:  # approve (final / PM)
            _require(request, Permission.APPROVE_PROGRESS.value)
            if sub.status != S.PENDING_PM:
                raise ValidationError({"status": "This submission isn't awaiting approval."})
            sub.approved_by = request.user
            sub.review_comment = comment or sub.review_comment
            sub.decided_at = timezone.now()
            if decision == "approve":
                sub.status = S.ACCEPTED
                sub.activity.progress_percent = sub.submitted_progress  # becomes official
                sub.activity.save(update_fields=["progress_percent", "updated_at"])
                _record_accepted_entry(sub)
            else:
                sub.status = S.PM_REJECTED
            sub.save(update_fields=["approved_by", "review_comment", "decided_at", "status", "updated_at"])

        notify_decision(sub, stage=self.stage, decision=decision, actor=request.user)
        return Response(SubmissionSerializer(sub).data)


class SubmissionImagesView(APIView):
    """POST supporting evidence photos onto a submission (staged client-side,
    then attached right after the submission is created)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, project_id, submission_id):
        project = _project(request, project_id)
        _require(request, Permission.SUBMIT_PROGRESS.value)
        sub = get_object_or_404(ProgressSubmission, pk=submission_id, project=project)
        image = request.FILES.get("image")
        if not image:
            raise ValidationError({"image": "No image provided."})
        if image.size > settings.MAX_UPLOAD_BYTES:
            raise ValidationError({"image": f"Image must be {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB or smaller."})
        if getattr(image, "content_type", None) not in ALLOWED_IMAGE_TYPES:
            raise ValidationError({"image": "Upload a JPG, PNG, or WebP image."})
        obj = SubmissionImage.objects.create(
            company=project.company, submission=sub, image=image,
            caption=request.data.get("caption", ""), uploaded_by=request.user,
        )
        return Response(SubmissionImageSerializer(obj).data, status=status.HTTP_201_CREATED)


class SubmissionImageFileView(APIView):
    """Stream a submission photo's bytes through an authed, tenant-scoped
    endpoint — no public URL, same on local disk and R2."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, submission_id, image_id):
        project = _project(request, project_id)
        _require_view(request)
        img = get_object_or_404(SubmissionImage, pk=image_id, submission_id=submission_id, submission__project=project)
        if not img.image:
            raise Http404
        content_type = mimetypes.guess_type(img.image.name)[0] or "application/octet-stream"
        return FileResponse(img.image.open("rb"), content_type=content_type)
