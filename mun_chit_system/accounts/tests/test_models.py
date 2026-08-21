from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Role, User


class UserManagerTests(TestCase):
    def test_create_user_hashes_password(self):
        user = User.objects.create_user(
            email="delegate@example.com", password="StrongPass123!", name="Delegate One"
        )
        self.assertNotEqual(user.password, "StrongPass123!")
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertTrue(user.password.startswith("pbkdf2_") or "$" in user.password)

    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="StrongPass123!", name="No Email")

    def test_email_is_normalized(self):
        user = User.objects.create_user(
            email="Test@EXAMPLE.com", password="StrongPass123!", name="Case Test"
        )
        self.assertEqual(user.email, "Test@example.com")

    def test_create_superuser_sets_flags(self):
        admin = User.objects.create_superuser(
            email="admin@example.com", password="StrongPass123!", name="Admin"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.role, Role.SUPER_ADMIN)
        self.assertTrue(admin.is_super_admin)

    def test_default_role_is_delegate(self):
        user = User.objects.create_user(
            email="d2@example.com", password="StrongPass123!", name="D2"
        )
        self.assertEqual(user.role, Role.DELEGATE)
        self.assertTrue(user.is_delegate)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(email="dup@example.com", password="StrongPass123!", name="A")
        with self.assertRaises(Exception):
            User.objects.create_user(email="dup@example.com", password="StrongPass123!", name="B")
