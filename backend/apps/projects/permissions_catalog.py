"""Per-project module permissions.

A project member holds an independent set of these on each project (stored on
ProjectMember.permissions). They decide which project modules/tabs the member
can see and act in — a second, project-scoped layer on top of company roles.

Admins bypass them: platform admins and holders of the company MANAGE_PROJECTS
permission implicitly hold every project permission on every project.
"""


class ProjectPermission:
    OVERVIEW = "overview"
    SCHEDULE = "schedule"
    SUBMIT_PROGRESS = "submit_progress"
    AREAS_OF_CONCERN = "areas_of_concern"
    FINANCES_VIEW = "finances_view"
    FINANCES_MANAGE = "finances_manage"
    SUBMITTALS = "submittals"
    REPORTS = "reports"
    TEAM = "team"
    REVIEW = "review"
    APPROVE = "approve"


# Grouped for the permission-matrix UI (label shown to the user per key).
PROJECT_PERMISSION_GROUPS = [
    ("Modules", [
        (ProjectPermission.OVERVIEW, "Overview"),
        (ProjectPermission.SCHEDULE, "Schedule"),
        (ProjectPermission.AREAS_OF_CONCERN, "Areas of Concern"),
        (ProjectPermission.FINANCES_VIEW, "Financials"),
        (ProjectPermission.SUBMITTALS, "Submittals / Documents"),
        (ProjectPermission.REPORTS, "Reports"),
        (ProjectPermission.TEAM, "Team & Access"),
    ]),
    ("Actions", [
        (ProjectPermission.SUBMIT_PROGRESS, "Submit / update progress"),
        (ProjectPermission.FINANCES_MANAGE, "Manage financials"),
        (ProjectPermission.REVIEW, "Review submissions"),
        (ProjectPermission.APPROVE, "Approve submissions"),
    ]),
]

ALL_PROJECT_PERMISSIONS = [key for _, items in PROJECT_PERMISSION_GROUPS for key, _ in items]

# Sensible starting point for a brand-new member if none are specified.
DEFAULT_PROJECT_PERMISSIONS = [ProjectPermission.OVERVIEW, ProjectPermission.SCHEDULE]


def project_permission_catalog():
    """Serializable catalog for the frontend permission matrix."""
    return [
        {"group": group, "permissions": [{"key": k, "label": lbl} for k, lbl in items]}
        for group, items in PROJECT_PERMISSION_GROUPS
    ]
