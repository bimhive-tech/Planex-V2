"""Notification fan-out for the approval workflow.

Kept separate from the views so the trigger points stay one-liners. Recipients
are resolved by permission (no per-project reviewer assignment exists yet):
submit -> everyone who can review; reviewer-approve -> everyone who can approve;
reject/accept -> the original submitter.
"""
from django.db.models import Q

from apps.accounts.constants import Permission
from apps.accounts.models import User

from .models import Notification, ProgressSubmission


def _users_with_permission(company, perm: str):
    """Active company users who can exercise `perm` — either through a role that
    grants it, or by being in the platform company (which holds everything)."""
    return User.objects.filter(company=company, is_active=True).filter(
        Q(company__is_platform_admin=True)
        | Q(memberships__is_active=True, memberships__role__permissions__contains=[perm])
    ).distinct()


def _activity_label(sub: ProgressSubmission) -> str:
    return sub.activity.name if sub.activity_id else "an activity"


def _bulk(company, recipients, *, actor, kind, message, project, submission):
    rows = [
        Notification(company=company, recipient=r, actor=actor, kind=kind,
                     message=message, project=project, submission=submission)
        for r in recipients if r.id != (actor.id if actor else None)
    ]
    if rows:
        Notification.objects.bulk_create(rows)


def notify_submitted(sub: ProgressSubmission):
    """A new submission entered the queue — tell the reviewers."""
    reviewers = _users_with_permission(sub.company, Permission.REVIEW_PROGRESS.value)
    name = sub.submitted_by.full_name if sub.submitted_by_id else "Someone"
    msg = f"{name} submitted “{_activity_label(sub)}” ({sub.submitted_progress}%) for review in {sub.project.name}."
    _bulk(sub.company, reviewers, actor=sub.submitted_by, kind=Notification.Kind.SUBMITTED,
          message=msg, project=sub.project, submission=sub)


def notify_decision(sub: ProgressSubmission, *, stage: str, decision: str, actor):
    """Fan out the outcome of a review/PM decision."""
    K = Notification.Kind
    label = _activity_label(sub)
    name = actor.full_name if actor else "A reviewer"

    if stage == "review" and decision == "approve":
        approvers = _users_with_permission(sub.company, Permission.APPROVE_PROGRESS.value)
        msg = f"“{label}” in {sub.project.name} passed review and is awaiting your approval."
        _bulk(sub.company, approvers, actor=actor, kind=K.REVIEW_APPROVED,
              message=msg, project=sub.project, submission=sub)
        return

    # Reject (either stage) or final accept -> notify the submitter.
    if not sub.submitted_by_id:
        return
    if decision == "reject":
        kind = K.REVIEW_REJECTED if stage == "review" else K.PM_REJECTED
        msg = f"{name} rejected your update to “{label}” in {sub.project.name}."
    else:  # final accept
        kind = K.ACCEPTED
        msg = f"Your update to “{label}” in {sub.project.name} was accepted ({sub.submitted_progress}%)."
    _bulk(sub.company, [sub.submitted_by], actor=actor, kind=kind,
          message=msg, project=sub.project, submission=sub)
