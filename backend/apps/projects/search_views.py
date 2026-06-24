"""Global search across a company's projects and activities. Tenant-isolated,
gated on project-view permission, and capped so it stays fast on large data."""
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .models import Activity, Project

_MIN_LEN = 2
_PROJECT_LIMIT = 8
_ACTIVITY_LIMIT = 10


def _scope_path(activity) -> str:
    node = activity.scope
    parts = []
    while node is not None:
        parts.append(node.name)
        node = node.parent
    return " / ".join(reversed(parts))


class GlobalSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        perms = request.user.effective_permissions()
        if Permission.VIEW_PROJECTS.value not in perms and Permission.MANAGE_PROJECTS.value not in perms:
            raise PermissionDenied("You don't have permission to search projects.")

        q = (request.query_params.get("q") or "").strip()
        if len(q) < _MIN_LEN:
            return Response({"projects": [], "activities": []})

        company = request.user.company
        projects = (Project.objects.filter(company=company)
                    .filter(Q(name__icontains=q) | Q(location__icontains=q) | Q(client_name__icontains=q))
                    .order_by("name")[:_PROJECT_LIMIT]
                    .values("id", "name", "location", "is_archived"))

        activity_qs = (Activity.objects.filter(company=company)
                       .filter(Q(name__icontains=q) | Q(code__icontains=q))
                       .select_related("project", "scope__parent__parent")
                       .order_by("name")[:_ACTIVITY_LIMIT])
        activities = [{
            "id": str(a.id), "name": a.name, "code": a.code,
            "project_id": str(a.project_id), "project_name": a.project.name,
            "path": _scope_path(a),
        } for a in activity_qs]

        return Response({
            "projects": [{
                "id": str(p["id"]), "name": p["name"],
                "location": p["location"], "is_archived": p["is_archived"],
            } for p in projects],
            "activities": activities,
        })
