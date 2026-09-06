"""Tests for Master Data: CRUD, permission gating, and the guards that stop a
delete from orphaning a project's stored value."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, Permission
from apps.accounts.models import Company, Membership, Role, User
from apps.projects.models import Project

from . import services as svc
from .models import Client, Consultant, Contractor, Currency, ProjectPriority, ProjectType


def _make_user(company, permissions):
    role = Role.objects.create(company=company, name="Tester", permissions=permissions)
    user = User.objects.create_user(email="t@example.com", password="pw12345!", company=company)
    Membership.objects.create(company=company, user=user, role=role, is_active=True)
    return user


class SeedDefaultMasterDataTests(TestCase):
    def test_seeds_currencies_types_and_priorities(self):
        company = Company.objects.create(name="Acme")
        svc.seed_default_master_data(company)

        self.assertEqual(ProjectType.objects.filter(company=company).count(), 4)
        self.assertEqual(ProjectPriority.objects.filter(company=company).count(), 3)
        currencies = Currency.objects.filter(company=company)
        self.assertEqual(currencies.count(), 4)
        self.assertEqual(currencies.get(code="AED").is_default, True)

    def test_is_idempotent(self):
        company = Company.objects.create(name="Acme")
        svc.seed_default_master_data(company)
        svc.seed_default_master_data(company)
        self.assertEqual(Currency.objects.filter(company=company).count(), 4)


class ServiceGuardTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        svc.seed_default_master_data(self.company)

    def test_set_default_currency_unsets_previous(self):
        aed = Currency.objects.get(company=self.company, code="AED")
        usd = Currency.objects.get(company=self.company, code="USD")
        svc.set_default_currency(currency=usd)
        aed.refresh_from_db()
        self.assertFalse(aed.is_default)
        self.assertTrue(Currency.objects.get(pk=usd.pk).is_default)

    def test_cannot_delete_default_currency(self):
        aed = Currency.objects.get(company=self.company, code="AED")
        with self.assertRaises(svc.MasterDataError):
            svc.delete_currency(currency=aed)

    def test_cannot_delete_currency_in_use(self):
        usd = Currency.objects.get(company=self.company, code="USD")
        Project.objects.create(company=self.company, name="P1", project_type="commercial", currency="USD")
        with self.assertRaises(svc.MasterDataError):
            svc.delete_currency(currency=usd)

    def test_cannot_delete_project_type_in_use(self):
        pt = ProjectType.objects.get(company=self.company, name="commercial")
        Project.objects.create(company=self.company, name="P1", project_type="commercial")
        with self.assertRaises(svc.MasterDataError):
            svc.delete_project_type(project_type=pt)

    def test_deleting_unused_project_type_succeeds(self):
        pt = ProjectType.objects.get(company=self.company, name="industrial")
        svc.delete_project_type(project_type=pt)
        self.assertFalse(ProjectType.objects.filter(pk=pt.pk).exists())

    def test_duplicate_currency_code_rejected(self):
        with self.assertRaises(svc.MasterDataError):
            svc.create_currency(company=self.company, code="AED", name="Dup", symbol="", is_default=False)

    def test_duplicate_project_type_name_rejected(self):
        with self.assertRaises(svc.MasterDataError):
            svc.create_project_type(company=self.company, name="commercial")


class MasterDataApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        svc.seed_default_master_data(self.company)
        self.client = APIClient()

    def test_reading_a_list_needs_only_project_visibility(self):
        """These lists populate the project form's dropdowns, so anyone who can
        see projects can read them — gating reads on MANAGE_MASTER_DATA left
        every non-admin project creator with dropdowns stuck on "Loading…".
        Nothing is disclosed that isn't already on the projects themselves."""
        user = _make_user(self.company, permissions=[Permission.VIEW_PROJECTS.value])
        self.client.force_authenticate(user)
        resp = self.client.get("/api/currencies/")
        self.assertEqual(resp.status_code, 200)

    def test_writing_still_requires_manage_master_data(self):
        user = _make_user(self.company, permissions=[Permission.VIEW_PROJECTS.value])
        self.client.force_authenticate(user)
        self.assertEqual(self.client.post("/api/currencies/", {"code": "GBP", "name": "Pound"}).status_code, 403)
        self.assertEqual(self.client.post("/api/clients/", {"name": "Nope"}).status_code, 403)

    def test_no_permission_at_all_is_still_refused(self):
        user = _make_user(self.company, permissions=[])
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/currencies/").status_code, 403)

    def test_list_and_create_currency(self):
        user = _make_user(self.company, permissions=COMPANY_ADMIN_PERMISSIONS)
        self.client.force_authenticate(user)

        resp = self.client.get("/api/currencies/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 4)

        resp = self.client.post("/api/currencies/", {"code": "gbp", "name": "British Pound"})
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["code"], "GBP")  # normalised uppercase

    def test_set_default_endpoint(self):
        user = _make_user(self.company, permissions=COMPANY_ADMIN_PERMISSIONS)
        self.client.force_authenticate(user)
        usd = Currency.objects.get(company=self.company, code="USD")

        resp = self.client.post(f"/api/currencies/{usd.pk}/set-default/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data["is_default"])
        self.assertFalse(Currency.objects.get(company=self.company, code="AED").is_default)

    def test_delete_in_use_project_type_returns_400_not_500(self):
        user = _make_user(self.company, permissions=COMPANY_ADMIN_PERMISSIONS)
        self.client.force_authenticate(user)
        Project.objects.create(company=self.company, name="P1", project_type="commercial")
        pt = ProjectType.objects.get(company=self.company, name="commercial")

        resp = self.client.delete(f"/api/project-types/{pt.pk}/")
        self.assertEqual(resp.status_code, 400)

    def test_create_project_priority_and_use_it_on_a_project(self):
        """The whole point: a custom value passes Project's own write serializer,
        which no longer restricts project_type/priority to the legacy 4/3."""
        user = _make_user(self.company, permissions=COMPANY_ADMIN_PERMISSIONS)
        self.client.force_authenticate(user)

        resp = self.client.post("/api/project-priorities/", {"name": "critical"})
        self.assertEqual(resp.status_code, 201, resp.data)

        resp = self.client.post("/api/projects/", {
            "name": "Custom Priority Project", "project_type": "commercial", "priority": "critical",
        })
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["priority"], "critical")


class StakeholderListTests(TestCase):
    """Clients / consultants / contractors — the lists behind the project
    form's stakeholder dropdowns."""

    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.other = Company.objects.create(name="Other")
        self.client = APIClient()

    def _admin(self):
        user = _make_user(self.company, permissions=COMPANY_ADMIN_PERMISSIONS)
        self.client.force_authenticate(user)
        return user

    def test_create_list_and_scope_to_one_company(self):
        self._admin()
        Client.objects.create(company=self.other, name="Someone else's client")

        resp = self.client.post("/api/clients/", {"name": "  Ministry of Housing  "})
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["name"], "Ministry of Housing")  # trimmed

        resp = self.client.get("/api/clients/")
        self.assertEqual([r["name"] for r in resp.data["results"]], ["Ministry of Housing"])

    def test_consultant_carries_phone_and_email(self):
        self._admin()
        resp = self.client.post(
            "/api/consultants/", {"name": "ECG", "phone": "+20 100", "email": "a@ecg.com"})
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual((resp.data["phone"], resp.data["email"]), ("+20 100", "a@ecg.com"))

    def test_duplicate_name_rejected_per_company(self):
        self._admin()
        self.client.post("/api/contractors/", {"name": "Sinai Sons"})
        dup = self.client.post("/api/contractors/", {"name": "Sinai Sons"})
        self.assertEqual(dup.status_code, 400)
        # ...but the same name is fine for a different company.
        Contractor.objects.create(company=self.other, name="Sinai Sons")

    def test_delete_blocked_while_a_project_still_names_it(self):
        self._admin()
        c = Client.objects.create(company=self.company, name="Ministry")
        Project.objects.create(company=self.company, name="P1", project_type="commercial",
                               client_name="Ministry")
        resp = self.client.delete(f"/api/clients/{c.id}/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("1 project", str(resp.data))

    def test_a_consultant_named_only_as_the_contractors_consultant_still_blocks_delete(self):
        """Consultant feeds two Project fields — either one counts as in use."""
        self._admin()
        c = Consultant.objects.create(company=self.company, name="Mentor")
        Project.objects.create(company=self.company, name="P1", project_type="commercial",
                               contractor_consultant="Mentor")
        self.assertEqual(self.client.delete(f"/api/consultants/{c.id}/").status_code, 400)

    def test_renaming_carries_the_new_name_onto_projects_using_it(self):
        """Otherwise the rename orphans them: their stored string would no
        longer match any list entry and the dropdown would read as blank."""
        self._admin()
        c = Consultant.objects.create(company=self.company, name="Old Name")
        mine = Project.objects.create(company=self.company, name="P1", project_type="commercial",
                                      consultant_name="Old Name", contractor_consultant="Old Name")
        theirs = Project.objects.create(company=self.other, name="P2", project_type="commercial",
                                        consultant_name="Old Name")

        resp = self.client.patch(f"/api/consultants/{c.id}/", {"name": "New Name"})
        self.assertEqual(resp.status_code, 200, resp.data)
        mine.refresh_from_db()
        self.assertEqual(mine.consultant_name, "New Name")
        self.assertEqual(mine.contractor_consultant, "New Name")
        theirs.refresh_from_db()
        self.assertEqual(theirs.consultant_name, "Old Name")  # another company's is untouched

    def test_another_companys_row_is_not_reachable(self):
        self._admin()
        theirs = Client.objects.create(company=self.other, name="Theirs")
        self.assertEqual(self.client.patch(f"/api/clients/{theirs.id}/", {"name": "x"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/clients/{theirs.id}/").status_code, 404)
