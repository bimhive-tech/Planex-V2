"""Progress submission + approval-chain API.

Flow: a field user with SUBMIT_PROGRESS submits a value (Pending Review); a user
with REVIEW_PROGRESS approves it to Pending PM Approval (or rejects); a user with
APPROVE_PROGRESS gives final acceptance (which updates the activity's official
progress) or rejects. Rejected submissions stay in history; the user resubmits a
new one. Everything is permission-gated, not role-gated.
"""
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .access import accessible_scope_ids
from .models import Activity, ProgressSubmission, Project


class SubmissionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    activity_name = serializers.CharField(source="activity.name", read_only=True)
    activity_path = serializers.SerializerMethodField()
    submitted_by_name = serializers.CharField(source="submitted_by.full_name", default="", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", default="", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.full_name", default="", read_only=True)

    class Meta:
        model = ProgressSubmission
        fields = [
            "id", "activity", "activity_name", "activity_path",
            "previous_progress", "submitted_progress", "status", "status_display",
            "note", "review_comment", "submitted_by_name", "reviewed_by_name",
            "approved_by_name", "created_at", "updated_at",
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


class InboxSubmissionSerializer(SubmissionSerializer):
    """Submission shape for the cross-project inbox — adds project identity."""

    project_id = serializers.UUIDField(source="project.id", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta(SubmissionSerializer.Meta):
        fields = SubmissionSerializer.Meta.fields + ["project_id", "project_name"]


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
        qs = project.submissions.select_related(*_SUBMISSIONS_QS)
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
        return Response(SubmissionSerializer(sub).data, status=status.HTTP_201_CREATED)


class ApprovalsInboxView(APIView):
    """Cross-project queue of submissions awaiting the current user's action.

    Reviewers (REVIEW_PROGRESS) see Pending Review; approvers (APPROVE_PROGRESS)
    see Pending PM Approval; a user with both sees both. Tenant-isolated to the
    caller's company. Decisions are taken via the per-project review/approve
    endpoints (the rows carry project_id)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        perms = request.user.effective_permissions()
        S = ProgressSubmission.Status
        can_review = Permission.REVIEW_PROGRESS.value in perms
        can_approve = Permission.APPROVE_PROGRESS.value in perms

        stages = []
        if can_review:
            stages.append(S.PENDING_REVIEW)
        if can_approve:
            stages.append(S.PENDING_PM)
        if not stages:
            return Response({"results": [], "review_count": 0, "approve_count": 0})

        base = ProgressSubmission.objects.filter(company=request.user.company, status__in=stages)
        review_count = base.filter(status=S.PENDING_REVIEW).count() if can_review else 0
        approve_count = base.filter(status=S.PENDING_PM).count() if can_approve else 0

        qs = base.select_related(*_SUBMISSIONS_QS, "project").order_by("-created_at")
        stage = request.query_params.get("stage")
        if stage == "review" and can_review:
            qs = qs.filter(status=S.PENDING_REVIEW)
        elif stage == "approve" and can_approve:
            qs = qs.filter(status=S.PENDING_PM)

        data = InboxSubmissionSerializer(qs[:200], many=True).data
        return Response({"results": data, "review_count": review_count, "approve_count": approve_count})


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
            sub.status = S.PENDING_PM if decision == "approve" else S.REVIEWER_REJECTED
            sub.save(update_fields=["reviewed_by", "review_comment", "status", "updated_at"])
        else:  # approve (final / PM)
            _require(request, Permission.APPROVE_PROGRESS.value)
            if sub.status != S.PENDING_PM:
                raise ValidationError({"status": "This submission isn't awaiting approval."})
            sub.approved_by = request.user
            sub.review_comment = comment or sub.review_comment
            if decision == "approve":
                sub.status = S.ACCEPTED
                sub.activity.progress_percent = sub.submitted_progress  # becomes official
                sub.activity.save(update_fields=["progress_percent", "updated_at"])
            else:
                sub.status = S.PM_REJECTED
            sub.save(update_fields=["approved_by", "review_comment", "status", "updated_at"])

        return Response(SubmissionSerializer(sub).data)
