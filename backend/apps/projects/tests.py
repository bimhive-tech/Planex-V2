"""Project API tests: tenant isolation, permission enforcement, CRUD, archive."""
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, Permission, SeededRole
from apps.accounts.models import Company, Membership, Role, User
from .imports import parse_sheet
from .models import Project


class ImportParserTests(SimpleTestCase):
    """The zone-sheet parser detects the grid (with or without a weight column)
    and averages each task across its subzones."""

    def test_detects_grid_with_weight_column(self):
        rows = [
            (None, None, 1, 2, 3),
            (None, None, "(A1)", "(A2)", "(A3)"),
            ("W", "Phase 1", 0.5, 0.5, 0.5),   # phase header (col-A "W") -> skipped
            (2.0, "Task1", 1, 1, 1),           # cells 100/100/100, weight 2
            (1.0, "Task2", 0, 0.5, 1),         # cells 0/50/100, weight 1
        ]
        sheet = parse_sheet(rows)
        self.assertEqual(sheet["subzones"], ["(A1)", "(A2)", "(A3)"])
        self.assertEqual(len(sheet["tasks"]), 2)
        self.assertEqual(sheet["tasks"][0]["weight"], 2.0)
        self.assertEqual(sheet["tasks"][0]["phase"], "Phase 1")
        self.assertEqual(sheet["tasks"][0]["cells"], [100.0, 100.0, 100.0])
        self.assertEqual(sheet["tasks"][1]["cells"], [0.0, 50.0, 100.0])

    def test_detects_grid_without_weight_column(self):
        # Like ZONE (B): codes start in column 1, name is column 0, no weight col.
        rows = [
            (None, 1, 2),
            (None, "(B1)", "(B2)"),
            ("summary", 0.4, 0.4),         # first row is the summary -> skipped
            ("Task1", 1, 0),              # cells 100/0, default weight 1
        ]
        sheet = parse_sheet(rows)
        self.assertEqual(sheet["subzones"], ["(B1)", "(B2)"])
        self.assertEqual(len(sheet["tasks"]), 1)
        self.assertEqual(sheet["tasks"][0]["weight"], 1.0)
        self.assertEqual(sheet["tasks"][0]["cells"], [100.0, 0.0])

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

        # Other tenant + its project + user (must stay invisible to company A).
        self.company_b = Company.objects.create(name="Globex")
        self.project_b = Project.objects.create(
            company=self.company_b, name="B Tower", project_type="commercial")
        self.user_b = User.objects.create_user(
            email="bob@globex.com", password=STRONG_PW, company=self.company_b)

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

    # ── Work hierarchy ────────────────────────────────────────────────────
    def test_build_structure_and_rollup(self):
        p = Project.objects.create(company=self.company_a, name="Hospital", project_type="commercial")
        self.login("admin@acme.com")
        base = f"/api/projects/{p.id}"
        # phase -> activity x2 with different weights/progress
        phase = self.client.post(f"{base}/scopes/", {"scope_type": "phase", "name": "Substructure"},
                                 content_type="application/json").json()
        a1 = self.client.post(f"{base}/activities/",
                              {"scope": phase["id"], "name": "Excavation", "weight": "3", "progress_percent": "100"},
                              content_type="application/json")
        a2 = self.client.post(f"{base}/activities/",
                              {"scope": phase["id"], "name": "Piling", "weight": "1", "progress_percent": "0"},
                              content_type="application/json")
        self.assertEqual(a1.status_code, 201, a1.content)
        self.assertEqual(a2.status_code, 201, a2.content)
        # overall = (100*3 + 0*1) / (3+1) = 75
        struct = self.client.get(f"{base}/structure/").json()
        self.assertEqual(struct["overall_progress"], 75.0)
        self.assertEqual(len(struct["scopes"]), 1)
        self.assertEqual(len(struct["activities"]), 2)

    def test_update_activity_progress_recomputes(self):
        p = Project.objects.create(company=self.company_a, name="Bridge", project_type="infrastructure")
        self.login("admin@acme.com")
        base = f"/api/projects/{p.id}"
        phase = self.client.post(f"{base}/scopes/", {"scope_type": "phase", "name": "Deck"},
                                 content_type="application/json").json()
        act = self.client.post(f"{base}/activities/",
                               {"scope": phase["id"], "name": "Pour", "weight": "1", "progress_percent": "0"},
                               content_type="application/json").json()
        self.client.patch(f"{base}/activities/{act['id']}/", {"progress_percent": "50"},
                          content_type="application/json")
        detail = self.client.get(f"{base}/").json()
        self.assertEqual(detail["overall_progress"], 50.0)
        self.assertEqual(detail["activity_count"], 1)

    def test_viewer_cannot_edit_structure(self):
        p = Project.objects.create(company=self.company_a, name="Depot2", project_type="industrial")
        self.login("viewer@acme.com")
        resp = self.client.post(f"/api/projects/{p.id}/scopes/", {"scope_type": "phase", "name": "X"},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_cannot_build_structure_on_other_company_project(self):
        self.login("admin@acme.com")
        resp = self.client.post(f"/api/projects/{self.project_b.id}/scopes/",
                                {"scope_type": "phase", "name": "X"}, content_type="application/json")
        self.assertEqual(resp.status_code, 404)

    # ── Team ──────────────────────────────────────────────────────────────
    def test_add_member_and_manager_surfaces_on_detail(self):
        p = Project.objects.create(company=self.company_a, name="Clinic", project_type="commercial")
        self.login("admin@acme.com")
        resp = self.client.post(
            f"/api/projects/{p.id}/members/",
            {"user_id": str(self.viewer.id), "role": "manager"}, content_type="application/json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["role_display"], "Project Manager")
        detail = self.client.get(f"/api/projects/{p.id}/").json()
        self.assertEqual(detail["manager_name"], self.viewer.full_name)
        self.assertEqual(detail["team_count"], 1)

    def test_cannot_add_user_from_other_company(self):
        p = Project.objects.create(company=self.company_a, name="Bridge2", project_type="infrastructure")
        self.login("admin@acme.com")
        resp = self.client.post(
            f"/api/projects/{p.id}/members/", {"user_id": str(self.user_b.id), "role": "member"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_viewer_cannot_add_member(self):
        p = Project.objects.create(company=self.company_a, name="Depot3", project_type="industrial")
        self.login("viewer@acme.com")
        resp = self.client.post(
            f"/api/projects/{p.id}/members/", {"user_id": str(self.admin.id), "role": "member"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_assignable_users_excludes_existing_members(self):
        p = Project.objects.create(company=self.company_a, name="Plaza", project_type="commercial")
        self.login("admin@acme.com")
        self.client.post(f"/api/projects/{p.id}/members/",
                         {"user_id": str(self.viewer.id), "role": "engineer"}, content_type="application/json")
        emails = {u["email"] for u in self.client.get(f"/api/projects/{p.id}/assignable-users/").json()}
        self.assertIn("admin@acme.com", emails)
        self.assertNotIn("viewer@acme.com", emails)  # already a member
