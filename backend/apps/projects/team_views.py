"""Project team API: list/add/update/remove members, and list assignable users.

Reads need VIEW_PROJECTS; writes need MANAGE_PROJECTS. Members must be users of
the same company as the project (tenant isolation).
"""
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission
from apps.accounts.models import User

from .models import Project, ProjectMember
from .serializers import ProjectMemberSerializer, ProjectMemberWriteSerializer


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

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        serializer = ProjectMemberWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # The user must belong to the same company.
        try:
            user = User.objects.get(pk=data["user_id"], company=project.company)
        except (User.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"user_id": "User not found in this company."})
        if project.members.filter(user=user).exists():
            raise ValidationError({"user_id": "Already a member of this project."})

        member = ProjectMember.objects.create(
            company=project.company, project=project, user=user, role=data["role"])
        member = ProjectMember.objects.select_related("user").get(pk=member.pk)
        return Response(ProjectMemberSerializer(member).data, status=status.HTTP_201_CREATED)


class ProjectMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, project, member_id):
        try:
            return ProjectMember.objects.select_related("user").get(pk=member_id, project=project)
        except (ProjectMember.DoesNotExist, ValueError, TypeError):
            raise NotFound("Member not found.")

    def patch(self, request, project_id, member_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        member = self._get(project, member_id)
        role = request.data.get("role")
        if role not in dict(ProjectMember.ProjectRole.choices):
            raise ValidationError({"role": "Invalid role."})
        member.role = role
        member.save(update_fields=["role", "updated_at"])
        return Response(ProjectMemberSerializer(member).data)

    def delete(self, request, project_id, member_id):
        project = _project(request, project_id)
        _require(request, Permission.MANAGE_PROJECTS.value)
        self._get(project, member_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
