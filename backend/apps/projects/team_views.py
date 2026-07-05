"""Project team API: list/add/remove members, and list assignable users.

Reads need VIEW_PROJECTS; writes need MANAGE_PROJECTS. Members must be users of
the same company as the project (tenant isolation). Module access comes from
each user's company role permissions (Settings -> Permissions) — nothing about
a membership is editable except scope grants (which parts of the project the
member can see; see MemberScopeAccessView).
"""
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import transaction
from apps.accounts.constants import Permission
from apps.accounts.models import User

from .models import Project, ProjectMember, ProjectScope, ProjectScopeAccess
from .serializers import ProjectMemberSerializer, ProjectMemberWriteSerializer


def _set_scope(project, user, scope_ids):
    """Replace a user's scope grants for the project (any scope level)."""
    scopes = list(project.scopes.filter(id__in=scope_ids)) if scope_ids else []
    ProjectScopeAccess.objects.filter(project=project, user=user).delete()
    ProjectScopeAccess.objects.bulk_create([
        ProjectScopeAccess(company=project.company, project=project, user=user, scope=s)
        for s in scopes
    ])
    return [str(s.id) for s in scopes]


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


class ProjectMemberListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view(request)
        members = project.members.select_related("user").all()
        return Response(ProjectMemberSerializer(members, many=True).data)

    @transaction.atomic
    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        # Backward compat: accept a single `user_id` from the old add-member form.
        payload = request.data
        if not payload.get("user_ids") and payload.get("user_id"):
            payload = {**payload, "user_ids": [payload["user_id"]]}
        serializer = ProjectMemberWriteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # All requested users must belong to the company and not already be members.
        users = list(User.objects.filter(id__in=data["user_ids"], company=project.company))
        if len(users) != len(set(data["user_ids"])):
            raise ValidationError({"user_ids": "One or more users were not found in this company."})
        already = set(project.members.filter(user__in=users).values_list("user_id", flat=True))

        created = []
        for user in users:
            if user.id in already:
                continue
            member = ProjectMember.objects.create(company=project.company, project=project, user=user)
            _set_scope(project, user, data["scope_ids"])
            created.append(member)

        members = ProjectMember.objects.select_related("user").filter(pk__in=[m.pk for m in created])
        return Response(ProjectMemberSerializer(members, many=True).data, status=status.HTTP_201_CREATED)


class ProjectMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, project, member_id):
        try:
            return ProjectMember.objects.select_related("user").get(pk=member_id, project=project)
        except (ProjectMember.DoesNotExist, ValueError, TypeError):
            raise NotFound("Member not found.")

    def delete(self, request, project_id, member_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        self._get(project, member_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectZonesView(APIView):
    """List the project's zones — for the access picker."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        zones = project.scopes.filter(scope_type=ProjectScope.ScopeType.ZONE).order_by("sort_order", "name")
        return Response([{"id": str(z.id), "name": z.name} for z in zones])


class MemberScopeAccessView(APIView):
    """GET the scopes a member is restricted to (empty = full access); PUT to set them."""

    permission_classes = [IsAuthenticated]

    def _member(self, project, member_id):
        try:
            return ProjectMember.objects.select_related("user").get(pk=member_id, project=project)
        except (ProjectMember.DoesNotExist, ValueError, TypeError):
            raise NotFound("Member not found.")

    def get(self, request, project_id, member_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        member = self._member(project, member_id)
        scope_ids = list(ProjectScopeAccess.objects.filter(project=project, user=member.user)
                         .values_list("scope_id", flat=True))
        # `zone_ids` kept for backward compat with existing callers.
        return Response({"scope_ids": [str(s) for s in scope_ids], "zone_ids": [str(s) for s in scope_ids]})

    def put(self, request, project_id, member_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        member = self._member(project, member_id)
        # Accept scope_ids (any level: zone/area/phase/activity); fall back to zone_ids.
        ids = request.data.get("scope_ids", request.data.get("zone_ids", []))
        saved = _set_scope(project, member.user, ids)
        return Response({"scope_ids": saved, "zone_ids": saved})


class AssignableUsersView(APIView):
    """Company users that can be added to the project (for the Add-member picker).
    Gated by MANAGE_PROJECTS so PMs can assign without needing MANAGE_USERS."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        taken = set(project.members.values_list("user_id", flat=True))
        users = (User.objects.filter(company=project.company, is_active=True)
                 .exclude(id__in=taken).order_by("email"))
        return Response([
            {"id": str(u.id), "email": u.email, "full_name": u.full_name} for u in users
        ])
