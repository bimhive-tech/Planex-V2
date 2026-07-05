"""Notification fan-out for the approval workflow.

Kept separate from the views so the trigger points stay one-liners. Recipients
are resolved in two tiers:
  1. Blanket admins (platform admins, company MANAGE_PROJECTS holders) always
     qualify — they have implicit access to every project regardless of
     explicit membership, so they should hear about all of them.
  2. Otherwise, the project's OWN team: members who hold the relevant company
     permission, preferring whoever is specifically assigned that
     responsibility (the project role — Reviewer for reviews, Manager for
     approvals) and falling back to any capable member if nobody is assigned.

This is what makes a project's "role" (Manager/Reviewer/Engineer/Member) more
than a label: it decides who gets notified first, instead of broadcasting to
every company-wide holder of the permission regardless of whether they're even
on this project.
"""
from django.db.models import Q

from apps.accounts.constants import Permission
from apps.accounts.models import User

from .models import Notification, ProgressSubmission, ProjectMember


def _blanket_admins(company):
    """Users who implicitly reach every project (platform admins, MANAGE_PROJECTS)."""
    return User.objects.filter(company=company, is_active=True).filter(
        Q(company__is_platform_admin=True)
        | Q(memberships__is_active=True, memberships__role__permissions__contains=[Permission.MANAGE_PROJECTS.value])
    )


def _project_recipients(project, perm: str, assigned_role: str):
    """Blanket admins, plus the project's capable team — preferring whoever is
    assigned `assigned_role`, falling back to any member who holds `perm` if
    nobody (or nobody with the permission) is assigned that role."""
    admins = _blanket_admins(project.company)
    capable = User.objects.filter(
        project_memberships__project=project, is_active=True,
    ).filter(
        Q(memberships__is_active=True, memberships__role__permissions__contains=[perm])
    )
    assigned = capable.filter(project_memberships__project=project, project_memberships__role=assigned_role)
    members = assigned if assigned.exists() else capable
    return (admins | members).distinct()


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
    reviewers = _project_recipients(sub.project, Permission.REVIEW_PROGRESS.value,
                                     ProjectMember.ProjectRole.REVIEWER)
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
        approvers = _project_recipients(sub.project, Permission.APPROVE_PROGRESS.value,
                                        ProjectMember.ProjectRole.MANAGER)
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
