from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from audit.models import AuditLog


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="login_test@example.com", password=self.password, name="Login Test"
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")

    def test_successful_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse("accounts:dashboard_redirect")))

    def test_successful_login_creates_audit_log(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": self.password},
        )
        self.assertTrue(
            AuditLog.objects.filter(actor=self.user, action="login_success").exists()
        )

    def test_wrong_password_rejected(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct email and password")

    def test_wrong_password_creates_failed_audit_log(self):
        self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": "wrong-password"},
        )
        self.assertTrue(AuditLog.objects.filter(action="login_failed").exists())

    def test_login_without_csrf_token_is_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 403)

    def test_rate_limiting_blocks_after_max_attempts(self):
        for _ in range(5):
            self.client.post(
                reverse("accounts:login"),
                {"username": self.user.email, "password": "wrong-password"},
            )
        # 6th attempt, even with the CORRECT password, should be blocked.
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": self.password},
        )
        self.assertContains(response, "Too many failed login attempts")
        # Session should not actually be authenticated.
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_rate_limit_is_per_identifier_not_global(self):
        other_user = User.objects.create_user(
            email="other_user@example.com", password="StrongPass123!", name="Other"
        )
        for _ in range(5):
            self.client.post(
                reverse("accounts:login"),
                {"username": self.user.email, "password": "wrong-password"},
            )
        # A different account from the same client should still be able to log in.
        response = self.client.post(
            reverse("accounts:login"),
            {"username": other_user.email, "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 302)


class LogoutTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="logout_test@example.com", password=self.password, name="Logout Test"
        )

    def test_logout_clears_session(self):
        self.client.login(username=self.user.email, password=self.password)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_creates_audit_log(self):
        self.client.login(username=self.user.email, password=self.password)
        self.client.post(reverse("accounts:logout"))
        self.assertTrue(AuditLog.objects.filter(actor=self.user, action="logout").exists())
