from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import User
from chits.models import Chit
from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference


class SeedDemoDataTests(TestCase):
    def _run(self, *args, **kwargs):
        out = StringIO()
        call_command("seed_demo_data", *args, stdout=out, **kwargs)
        return out.getvalue()

    @override_settings(DEBUG=True)
    def test_creates_conference_committees_and_rooms(self):
        self._run()
        conference = Conference.objects.get(name="Global Horizons MUN 2026")
        self.assertEqual(Committee.objects.filter(conference=conference).count(), 3)
        self.assertEqual(conference.rooms.count(), 3)

    @override_settings(DEBUG=True)
    def test_creates_delegates_and_staff_with_working_login(self):
        self._run()
        delegate = User.objects.get(email="usa.unsc@demo.mun")
        self.assertTrue(delegate.check_password("DemoPass123!"))
        self.assertTrue(
            CountryAssignment.objects.filter(user=delegate, country_code="USA").exists()
        )

        chair = User.objects.get(email="unsc.chair@demo.mun")
        self.assertTrue(
            CommitteeStaff.objects.filter(user=chair, role=CommitteeStaff.StaffRole.CHAIR).exists()
        )

    @override_settings(DEBUG=True)
    def test_creates_sample_chits_covering_multiple_statuses(self):
        self._run()
        conference = Conference.objects.get(name="Global Horizons MUN 2026")
        statuses = set(Chit.objects.filter(conference=conference).values_list("status", flat=True))
        # At minimum, submitted / read / replied / archived should all be represented
        # so every dashboard queue and filter has something to show.
        self.assertTrue({"submitted", "read", "replied", "archived"}.issubset(statuses))

    @override_settings(DEBUG=True)
    def test_running_twice_is_idempotent(self):
        self._run()
        conference_count_1 = Conference.objects.count()
        user_count_1 = User.objects.count()
        chit_count_1 = Chit.objects.count()

        self._run()
        self.assertEqual(Conference.objects.count(), conference_count_1)
        self.assertEqual(User.objects.count(), user_count_1)
        self.assertEqual(Chit.objects.count(), chit_count_1)

    @override_settings(DEBUG=False)
    def test_refuses_to_run_outside_debug_without_force(self):
        with self.assertRaises(CommandError):
            self._run()
        self.assertFalse(Conference.objects.filter(name="Global Horizons MUN 2026").exists())

    @override_settings(DEBUG=False)
    def test_force_flag_bypasses_debug_check(self):
        self._run("--force")
        self.assertTrue(Conference.objects.filter(name="Global Horizons MUN 2026").exists())

    @override_settings(DEBUG=True)
    def test_prints_credentials_summary(self):
        output = self._run()
        self.assertIn("DemoPass123!", output)
        self.assertIn("super@demo.mun", output)
        self.assertIn("admin@demo.mun", output)
