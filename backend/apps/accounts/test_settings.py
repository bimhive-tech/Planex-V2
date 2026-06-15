"""Settings module tests: tenant isolation, permission enforcement, perm filtering."""
from django.test import TestCase
from django.urls import reverse

from .constants import COMPANY_ADMIN_PERMISSIONS, Permission, SeededRole
from .models import Company, Membership, Role, User

STRONG_PW = "Str0ngPassw0rd!"


class SettingsApiTests(TestCase):
    def setUp(self):
        # Platform (admin) company + superadmin.
        self.platform = Company.objects.create(name="Admin", is_platform_admin=True)
        self.platform_role = Role.objects.create(
            company=self.platform, name=SeededRole.PLATFORM_ADMIN,
            is_platform_role=True, permissions=[p.value for p in Permission],
        )
        self.superadmin = User.objects.create_user(
            email="super@planex.app", password=STRONG_PW, company=self.platform)
        Membership.objects.create(company=self.platform, user=self.superadmin, role=self.platform_role)

        # Company A: admin (Company Admin role) + a viewer (view_projects only).
        self.company_a = Company.objects.create(name="Acme")
        self.admin_role_a = Role.objects.create(
            company=self.company_a, name=SeededRole.COMPANY_ADMIN,
            permissions=COMPANY_ADMIN_PERMISSIONS)
        self.admin_a = User.objects.create_user(
            email="admin@acme.com", password=STRONG_PW, company=self.company_a)
        Membership.objects.create(company=self.company_a, user=self.admin_a, role=self.admin_role_a)

        self.viewer_role_a = Role.objects.create(
            company=self.company_a, name="Viewer", permissions=[Permission.VIEW_PROJECTS.value])
        self.viewer_a = User.objects.create_user(
            email="viewer@acme.com", password=STRONG_PW, company=self.company_a)
        Membership.objects.create(company=self.company_a, user=self.viewer_a, role=self.viewer_role_a)

        # Company B (separate tenant).
        self.company_b = Company.objects.create(name="Globex")
        self.user_b = User.objects.create_user(
            email="bob@globex.com", password=STRONG_PW, company=self.company_b)

    def login(self, email):
        resp = self.client.post(
            reverse("auth-login"),
            {"email": email, "password": STRONG_PW},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    # ── Companies (platform only) ─────────────────────────────────────────
    def test_platform_admin_creates_company_with_default_role(self):
        self.login("super@planex.app")
        resp = self.client.post("/api/companies/", {"name": "Initech"}, content_type="application/json")
        self.assertEqual(resp.status_code, 201, resp.content)
        company = Company.objects.get(name="Initech")
        self.assertTrue(
            Role.objects.filter(company=company, name=SeededRole.COMPANY_ADMIN).exists())

    def test_company_admin_cannot_access_companies(self):
        self.login("admin@acme.com")
        self.assertEqual(self.client.get("/api/companies/").status_code, 403)

    # ── Roles (permission filtering) ──────────────────────────────────────
    def test_company_admin_creates_role_drops_platform_permissions(self):
        self.login("admin@acme.com")
        resp = self.client.post(
            "/api/roles/",
            {"name": "Engineer", "permissions": [
                Permission.SUBMIT_PROGRESS.value, Permission.MANAGE_COMPANIES.value]},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["permissions"], [Permission.SUBMIT_PROGRESS.value])

    # ── Users (create + isolation) ────────────────────────────────────────
    def test_company_admin_creates_and_lists_users_in_own_company(self):
        self.login("admin@acme.com")
        resp = self.client.post(
            "/api/users/",
            {"email": "eng@acme.com", "password": STRONG_PW, "role_ids": [str(self.viewer_role_a.id)]},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["roles"], ["Viewer"])

        emails = {u["email"] for u in self.client.get("/api/users/").json()["results"]}
        self.assertIn("eng@acme.com", emails)
        self.assertNotIn("bob@globex.com", emails)  # company B isolated

    def test_company_admin_cannot_target_other_company_via_param(self):
        self.login("admin@acme.com")
        # Non-platform user: ?company= is ignored, stays scoped to own company.
        resp = self.client.get(f"/api/users/?company={self.company_b.id}")
        emails = {u["email"] for u in resp.json()["results"]}
        self.assertNotIn("bob@globex.com", emails)

    def test_platform_admin_can_target_company_via_param(self):
        self.login("super@planex.app")
        resp = self.client.get(f"/api/users/?company={self.company_b.id}")
        emails = {u["email"] for u in resp.json()["results"]}
        self.assertIn("bob@globex.com", emails)

    def test_viewer_without_manage_users_is_forbidden(self):
        self.login("viewer@acme.com")
        self.assertEqual(self.client.get("/api/users/").status_code, 403)

    # ── Company info ──────────────────────────────────────────────────────
    def test_company_info_get_and_edit_permission(self):
        self.login("admin@acme.com")
        self.assertEqual(self.client.get("/api/company/").json()["name"], "Acme")
        resp = self.client.patch(
            "/api/company/", {"phone_number": "+100"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["phone_number"], "+100")

    def test_viewer_cannot_edit_company_info(self):
        self.login("viewer@acme.com")
        resp = self.client.patch(
            "/api/company/", {"phone_number": "+999"}, content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    # ── Default + locked roles ────────────────────────────────────────────
    def test_create_company_seeds_default_roles(self):
        self.login("super@planex.app")
        resp = self.client.post("/api/companies/", {"name": "Initech"}, content_type="application/json")
        self.assertEqual(resp.status_code, 201, resp.content)
        company = Company.objects.get(name="Initech")
        ca = Role.objects.get(company=company, name=SeededRole.COMPANY_ADMIN)
        usr = Role.objects.get(company=company, name=SeededRole.USER)
        self.assertTrue(ca.is_system and ca.is_locked)
        self.assertTrue(usr.is_system and not usr.is_locked)

    def test_locked_company_admin_role_cannot_be_edited_or_deleted(self):
        # Mark Acme's admin role as the locked default.
        self.admin_role_a.is_system = self.admin_role_a.is_locked = True
        self.admin_role_a.save()
        self.login("admin@acme.com")
        edit = self.client.patch(f"/api/roles/{self.admin_role_a.id}/",
                                 {"name": "Renamed"}, content_type="application/json")
        self.assertEqual(edit.status_code, 403)
        delete = self.client.delete(f"/api/roles/{self.admin_role_a.id}/")
        self.assertEqual(delete.status_code, 403)

    def test_editable_default_user_role_name_can_change(self):
        user_role = Role.objects.create(
            company=self.company_a, name=SeededRole.USER,
            permissions=[Permission.VIEW_PROJECTS.value], is_system=True, is_locked=False)
        self.login("admin@acme.com")
        resp = self.client.patch(f"/api/roles/{user_role.id}/",
                                 {"name": "Member"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["name"], "Member")
        # ...but still not deletable (system role).
        self.assertEqual(self.client.delete(f"/api/roles/{user_role.id}/").status_code, 403)

    def test_permission_matrix_toggle_updates_role(self):
        self.login("admin@acme.com")
        resp = self.client.patch(
            f"/api/roles/{self.viewer_role_a.id}/",
            {"permissions": [Permission.VIEW_PROJECTS.value, Permission.SUBMIT_PROGRESS.value]},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(set(resp.json()["permissions"]),
                         {Permission.VIEW_PROJECTS.value, Permission.SUBMIT_PROGRESS.value})

    # ── Deletion ──────────────────────────────────────────────────────────
    def test_platform_admin_deletes_company_cascades(self):
        self.login("super@planex.app")
        resp = self.client.delete(f"/api/companies/{self.company_b.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Company.objects.filter(pk=self.company_b.id).exists())
        self.assertFalse(User.objects.filter(email="bob@globex.com").exists())

    def test_cannot_delete_platform_company(self):
        self.login("super@planex.app")
        self.assertEqual(self.client.delete(f"/api/companies/{self.platform.id}/").status_code, 403)

    def test_delete_user_and_cannot_delete_self(self):
        self.login("admin@acme.com")
        ok = self.client.delete(f"/api/users/{self.viewer_a.id}/")
        self.assertEqual(ok.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.viewer_a.id).exists())
        # Can't delete yourself.
        self.assertEqual(self.client.delete(f"/api/users/{self.admin_a.id}/").status_code, 403)

    def test_edit_user_email_and_password(self):
        self.login("admin@acme.com")
        resp = self.client.patch(
            f"/api/users/{self.viewer_a.id}/",
            {"email": "newviewer@acme.com", "password": "An0therStr0ng!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.viewer_a.refresh_from_db()
        self.assertEqual(self.viewer_a.email, "newviewer@acme.com")
        self.assertTrue(self.viewer_a.check_password("An0therStr0ng!"))
