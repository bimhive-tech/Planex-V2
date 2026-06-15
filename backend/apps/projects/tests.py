"""Project API tests: tenant isolation, permission enforcement, CRUD, archive."""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, Permission, SeededRole
from apps.accounts.models import Company, Membership, Role, User
from .models import Project

STRONG_PW = "Str0ngPassw0rd!"


class ProjectApiTests(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Acme")
        self.admin_role = Role.objects.create(
            company=self.company_a, name=SeededRole.COMPANY_ADMIN,
            permissions=COMPANY_ADMIN_PERMISSIONS)
        self.admin = User.objects.create_user(
            email="admin@acme.com", password=STRONG_PW, company=self.company_a)
        Membership.objects.create(company=self.company_a, user=self.admin, role=self.admin_role)

        self.viewer_role = Role.objects.create(
            company=self.company_a, name="Viewer", permissions=[Permission.VIEW_PROJECTS.value])
        self.viewer = User.objects.create_user(
            email="viewer@acme.com", password=STRONG_PW, company=self.company_a)
        Membership.objects.create(company=self.company_a, user=self.viewer, role=self.viewer_role)

        # Other tenant + its project (must stay invisible to company A).
        self.company_b = Company.objects.create(name="Globex")
        self.project_b = Project.objects.create(
            company=self.company_b, name="B Tower", project_type="commercial")

    def login(self, email):
        resp = self.client.post(
            reverse("auth-login"), {"email": email, "password": STRONG_PW},
            content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_create_requires_manage_projects(self):
        self.login("viewer@acme.com")
        resp = self.client.post(
            "/api/projects/", {"name": "Mall", "project_type": "commercial"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_admin_creates_and_lists_project(self):
        self.login("admin@acme.com")
        resp = self.client.post(
            "/api/projects/",
            {"name": "Mall", "project_type": "commercial", "location": "Dubai"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["project_type_display"], "Commercial")

        names = {p["name"] for p in self.client.get("/api/projects/").json()["results"]}
        self.assertIn("Mall", names)
        self.assertNotIn("B Tower", names)  # company B isolated

    def test_viewer_can_read(self):
        Project.objects.create(company=self.company_a, name="Villa", project_type="residential")
        self.login("viewer@acme.com")
        self.assertEqual(self.client.get("/api/projects/").status_code, 200)

    def test_cannot_access_other_company_project(self):
        self.login("admin@acme.com")
        self.assertEqual(self.client.get(f"/api/projects/{self.project_b.id}/").status_code, 404)

    def test_archive_and_filter(self):
        p = Project.objects.create(company=self.company_a, name="Depot", project_type="industrial")
        self.login("admin@acme.com")
        self.client.patch(f"/api/projects/{p.id}/", {"is_archived": True},
                          content_type="application/json")
        active = {x["name"] for x in self.client.get("/api/projects/?status=active").json()["results"]}
        archived = {x["name"] for x in self.client.get("/api/projects/?status=archived").json()["results"]}
        self.assertNotIn("Depot", active)
        self.assertIn("Depot", archived)

    def test_duplicate_name_rejected(self):
        Project.objects.create(company=self.company_a, name="Tower", project_type="commercial")
        self.login("admin@acme.com")
        resp = self.client.post("/api/projects/", {"name": "Tower", "project_type": "commercial"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)
