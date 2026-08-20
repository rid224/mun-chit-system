from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from committees.models import Committee, CountryAssignment
from conferences.models import Conference, Room


class CommitteeSelectorTests(TestCase):
    def setUp(self):
        self.conference = Conference.objects.create(
            name="Selector Test MUN", year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 3)
        )
        self.room_a = Room.objects.create(conference=self.conference, name="Room A")
        self.room_b = Room.objects.create(conference=self.conference, name="Room B")
        self.committee_a = Committee.objects.create(
            conference=self.conference, name="UNSC", abbreviation="UNSC", room=self.room_a
        )
        self.committee_b = Committee.objects.create(
            conference=self.conference, name="ECOSOC", abbreviation="ECOSOC", room=self.room_b
        )

        self.password = "StrongPass123!"

        self.single_delegate = User.objects.create_user(
            email="single@example.com", password=self.password, name="Single Delegate"
        )
        CountryAssignment.objects.create(
            user=self.single_delegate,
            committee=self.committee_a,
            country_name="India",
            country_code="IND",
        )

        self.multi_delegate = User.objects.create_user(
            email="multi@example.com", password=self.password, name="Multi Delegate"
        )
        CountryAssignment.objects.create(
            user=self.multi_delegate,
            committee=self.committee_a,
            country_name="France",
            country_code="FRA",
        )
        CountryAssignment.objects.create(
            user=self.multi_delegate,
            committee=self.committee_b,
            country_name="Brazil",
            country_code="BRA",
        )

    def _login(self, user):
        self.client.login(username=user.email, password=self.password)

    def test_single_committee_user_skips_selector(self):
        self._login(self.single_delegate)
        response = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(response, reverse("chits:delegate_dashboard"))

    def test_multi_committee_user_is_routed_to_selector(self):
        self._login(self.multi_delegate)
        response = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(response, reverse("committees:select"))

    def test_selector_lists_both_committees(self):
        self._login(self.multi_delegate)
        response = self.client.get(reverse("committees:select"))
        self.assertContains(response, "UNSC")
        self.assertContains(response, "ECOSOC")

    def test_selecting_a_committee_sets_session_and_redirects(self):
        self._login(self.multi_delegate)
        response = self.client.post(
            reverse("committees:select"), {"committee_id": str(self.committee_b.id)}
        )
        self.assertRedirects(response, reverse("chits:delegate_dashboard"))
        self.assertEqual(self.client.session["active_committee_id"], str(self.committee_b.id))

    def test_selecting_a_committee_the_user_does_not_belong_to_is_rejected(self):
        self._login(self.single_delegate)
        # single_delegate has no assignment in committee_b
        response = self.client.post(
            reverse("committees:select"), {"committee_id": str(self.committee_b.id)}
        )
        self.assertEqual(response.status_code, 404)

    def test_dashboard_reflects_the_selected_committee(self):
        self._login(self.multi_delegate)
        self.client.post(
            reverse("committees:select"), {"committee_id": str(self.committee_b.id)}
        )
        response = self.client.get(reverse("chits:delegate_dashboard"))
        self.assertContains(response, "ECOSOC")
        self.assertContains(response, "Brazil")
