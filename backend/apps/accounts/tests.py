"""Auth flow tests: login sets cookies, /me works, bad creds rejected."""
from django.test import TestCase
from django.urls import reverse

from .constants import ALL_PERMISSIONS, SeededRole
from .models import Company, Membership, Role, User


class AuthFlowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Admin", is_platform_admin=True)
        self.role = Role.objects.create(
            company=self.company, name=SeededRole.PLATFORM_ADMIN,
            is_platform_role=True, permissions=ALL_PERMISSIONS,
        )
        self.user = User.objects.create_user(
            email="superadmin@planex.app", password="12345678", company=self.company,
        )
        Membership.objects.create(company=self.company, user=self.user, role=self.role)

    def test_login_sets_cookies_and_returns_profile(self):
        resp = self.client.post(
            reverse("auth-login"),
            {"email": "superadmin@planex.app", "password": "12345678"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("planex_access", resp.cookies)
        self.assertIn("planex_refresh", resp.cookies)
        self.assertTrue(resp.json()["is_platform_admin"])
        self.assertEqual(set(resp.json()["permissions"]), set(ALL_PERMISSIONS))

    def test_login_rejects_bad_password(self):
        resp = self.client.post(
            reverse("auth-login"),
            {"email": "superadmin@planex.app", "password": "wrong"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.json())

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 401)

    def test_me_returns_profile_after_login(self):
        self.client.post(
            reverse("auth-login"),
            {"email": "superadmin@planex.app", "password": "12345678"},
            content_type="application/json",
        )
        resp = self.client.get(reverse("auth-me"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "superadmin@planex.app")
