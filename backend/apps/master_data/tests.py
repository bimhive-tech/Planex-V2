"""Tests for Master Data: CRUD, permission gating, and the guards that stop a
delete from orphaning a project's stored value."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, Permission
from apps.accounts.models import Company, Membership, Role, User
from apps.projects.models import Project

from . import services as svc
from .models import Currency, ProjectPriority, ProjectType


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

    def test_requires_permission(self):
        user = _make_user(self.company, permissions=[Permission.VIEW_PROJECTS.value])
        self.client.force_authenticate(user)
        resp = self.client.get("/api/currencies/")
        self.assertEqual(resp.status_code, 403)

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
