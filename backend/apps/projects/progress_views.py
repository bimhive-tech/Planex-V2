"""Dated progress entries + their photos.

Record progress for an activity on a date (<= today; back-dating allowed),
attach optional photos with captions, browse photo history by scope/date, and
delete photos (gated by DELETE_PROGRESS_IMAGES). Updates the activity's current
% to its latest-dated entry."""
import mimetypes

from django.conf import settings
from django.db.models import Q
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

from .models import Activity, ProgressEntry, ProgressImage, Project, ProjectScope

ALLOWED = {"image/jpeg", "image/png", "image/webp"}


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require_view(request):
    perms = request.user.effective_permissions()
    if not ({Permission.VIEW_PROJECTS, Permission.MANAGE_PROJECTS} & perms):
        raise PermissionDenied("You don't have permission to view this.")


def _require_record(request):
    perms = request.user.effective_permissions()
    if not ({Permission.SUBMIT_PROGRESS, Permission.MANAGE_PROJECTS} & perms):
        raise PermissionDenied("You don't have permission to record progress.")


def _can_edit_entry(user, entry):
    """The author may edit/delete their own readings; managers any reading."""
    if Permission.MANAGE_PROJECTS in user.effective_permissions():
        return True
    return entry.recorded_by_id == user.id


def _sync_activity(activity):
    """Keep the activity's current % equal to its latest-dated progress entry."""
    latest = activity.progress_entries.order_by("-date", "-created_at").first()
    if latest:
        activity.progress_percent = latest.progress_percent
        activity.save(update_fields=["progress_percent"])


class ProgressImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    date = serializers.DateField(source="entry.date", read_only=True)
    activity_id = serializers.CharField(source="entry.activity_id", read_only=True)
    activity_name = serializers.CharField(source="entry.activity.name", read_only=True)
    phase_name = serializers.CharField(source="entry.activity.phase_name", read_only=True, default="")
    subzone_code = serializers.CharField(source="entry.activity.subzone_code", read_only=True, default="")
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True, default="")

    class Meta:
        model = ProgressImage
        fields = ["id", "url", "caption", "date", "activity_id", "activity_name",
                  "phase_name", "subzone_code", "uploaded_by_name", "created_at"]

    def get_url(self, obj):
        return f"/api/projects/{obj.entry.project_id}/progress-images/{obj.id}/file/" if obj.image else ""


class ProgressEntrySerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(source="recorded_by.full_name", read_only=True, default="")
    can_edit = serializers.SerializerMethodField()
    images = ProgressImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProgressEntry
        fields = ["id", "date", "progress_percent", "note", "recorded_by_name",
                  "can_edit", "images", "created_at"]

    def get_can_edit(self, obj):
        request = self.context.get("request")
        return bool(request) and _can_edit_entry(request.user, obj)


class ActivityProgressView(APIView):
    """GET an activity's dated progress history; POST a new dated reading."""

    permission_classes = [IsAuthenticated]

    def _activity(self, project, activity_id):
        try:
            return Activity.objects.get(pk=activity_id, project=project)
        except (Activity.DoesNotExist, ValueError, TypeError):
            raise NotFound("Activity not found.")

    def get(self, request, project_id, activity_id):
        project = _project(request, project_id)
        _require_view(request)
        activity = self._activity(project, activity_id)
        qs = activity.progress_entries.select_related("recorded_by").prefetch_related("images")
        return Response(ProgressEntrySerializer(qs, many=True, context={"request": request}).data)

    def post(self, request, project_id, activity_id):
        project = _project(request, project_id)
        _require_record(request)
        activity = self._activity(project, activity_id)
        try:
            pct = float(request.data.get("progress_percent"))
        except (TypeError, ValueError):
            raise ValidationError({"progress_percent": "A number 0–100 is required."})
        if not 0 <= pct <= 100:
            raise ValidationError({"progress_percent": "Must be between 0 and 100."})
        date = request.data.get("date") or str(timezone.localdate())
        if date > str(timezone.localdate()):
            raise ValidationError({"date": "You can't record progress for a future date."})
        entry = ProgressEntry.objects.create(
            company=project.company, project=project, activity=activity,
            date=date, progress_percent=pct, note=request.data.get("note", ""),
            recorded_by=request.user,
        )
        _sync_activity(activity)
        return Response(ProgressEntrySerializer(entry, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)


class ProgressEntryDetailView(APIView):
    """Edit (PATCH) or remove (DELETE) a progress reading (author their own;
    managers any)."""

    permission_classes = [IsAuthenticated]

    def _entry(self, project, entry_id):
        return get_object_or_404(
            ProgressEntry.objects.select_related("activity", "recorded_by"),
            pk=entry_id, project=project,
        )

    def patch(self, request, project_id, entry_id):
        project = _project(request, project_id)
        _require_record(request)
        entry = self._entry(project, entry_id)
        if not _can_edit_entry(request.user, entry):
            raise PermissionDenied("This entry can no longer be edited.")

        if "progress_percent" in request.data:
            try:
                pct = float(request.data["progress_percent"])
            except (TypeError, ValueError):
                raise ValidationError({"progress_percent": "A number 0–100 is required."})
            if not 0 <= pct <= 100:
                raise ValidationError({"progress_percent": "Must be between 0 and 100."})
            entry.progress_percent = pct
        if "date" in request.data:
            date = request.data["date"]
            if not date or date > str(timezone.localdate()):
                raise ValidationError({"date": "Pick a valid date that isn't in the future."})
            entry.date = date
        if "note" in request.data:
            entry.note = request.data["note"]
        entry.save()
        _sync_activity(entry.activity)
        return Response(ProgressEntrySerializer(entry, context={"request": request}).data)

    def delete(self, request, project_id, entry_id):
        project = _project(request, project_id)
        _require_record(request)
        entry = self._entry(project, entry_id)
        if not _can_edit_entry(request.user, entry):
            raise PermissionDenied("This entry can no longer be edited.")
        activity = entry.activity
        entry.delete()
        _sync_activity(activity)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProgressEntryImagesView(APIView):
    """POST a photo (with optional caption) onto a progress entry."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, project_id, entry_id):
        project = _project(request, project_id)
        _require_record(request)
        entry = get_object_or_404(ProgressEntry, pk=entry_id, project=project)
        image = request.FILES.get("image")
        if not image:
            raise ValidationError({"image": "No image provided."})
        if image.size > settings.MAX_UPLOAD_BYTES:
            raise ValidationError({"image": f"Image must be {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB or smaller."})
        if getattr(image, "content_type", None) not in ALLOWED:
            raise ValidationError({"image": "Upload a JPG, PNG, or WebP image."})
        obj = ProgressImage.objects.create(
            company=project.company, entry=entry, image=image,
            caption=request.data.get("caption", ""), uploaded_by=request.user,
        )
        return Response(ProgressImageSerializer(obj).data, status=status.HTTP_201_CREATED)


class ProgressImagesListView(APIView):
    """Browse progress photos under a scope subtree (or one activity), filtered
    by date — the history viewer."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        qs = ProgressImage.objects.filter(entry__project=project).select_related(
            "entry", "entry__activity", "uploaded_by")

        scope_id = request.query_params.get("scope")
        if scope_id:
            qs = qs.filter(entry__activity__scope_id__in=_subtree_scope_ids(project, scope_id))
        activity_id = request.query_params.get("activity")
        if activity_id:
            qs = qs.filter(entry__activity_id=activity_id)
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            qs = qs.filter(entry__date__gte=date_from)
        if date_to:
            qs = qs.filter(entry__date__lte=date_to)

        qs = qs.order_by("-entry__date", "-created_at")[:500]
        return Response(ProgressImageSerializer(qs, many=True).data)


class ProgressImageDetailView(APIView):
    """Delete a progress photo (needs DELETE_PROGRESS_IMAGES or MANAGE_PROJECTS)."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, project_id, image_id):
        project = _project(request, project_id)
        perms = request.user.effective_permissions()
        if not ({Permission.DELETE_PROGRESS_IMAGES, Permission.MANAGE_PROJECTS} & perms):
            raise PermissionDenied("You don't have permission to delete progress photos.")
        img = get_object_or_404(ProgressImage, pk=image_id, entry__project=project)
        if img.image:
            img.image.delete(save=False)
        img.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProgressImageFileView(APIView):
    """Stream a private progress photo's bytes (authed)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, image_id):
        project = _project(request, project_id)
        _require_view(request)
        img = get_object_or_404(ProgressImage, pk=image_id, entry__project=project)
        if not img.image:
            raise Http404
        content_type = mimetypes.guess_type(img.image.name)[0] or "application/octet-stream"
        return FileResponse(img.image.open("rb"), content_type=content_type)


def _subtree_scope_ids(project, root_id):
    """All scope ids in the subtree rooted at `root_id` (inclusive)."""
    children = {}
    for sid, pid in project.scopes.values_list("id", "parent_id"):
        if pid:
            children.setdefault(str(pid), []).append(str(sid))
    out, stack = [], [str(root_id)]
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(children.get(node, []))
    return out
