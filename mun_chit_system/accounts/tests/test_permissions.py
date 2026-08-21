from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference, Room


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.conference = Conference.objects.create(
            name="Access Test MUN", year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 3)
        )
        self.room = Room.objects.create(conference=self.conference, name="Room A")
        self.committee = Committee.objects.create(
            conference=self.conference, name="UNSC", abbreviation="UNSC", room=self.room
        )

        self.password = "StrongPass123!"

        self.delegate = User.objects.create_user(
            email="delegate@example.com", password=self.password, name="Delegate"
        )
        CountryAssignment.objects.create(
            user=self.delegate, committee=self.committee, country_name="India", country_code="IND"
        )

        self.eb_member = User.objects.create_user(
            email="eb@example.com", password=self.password, name="EB", role="executive_board"
        )
        CommitteeStaff.objects.create(
            user=self.eb_member, committee=self.committee, role=CommitteeStaff.StaffRole.CHAIR
        )

        self.plain_user = User.objects.create_user(
            email="plain@example.com", password=self.password, name="No Assignment"
        )

        self.committee_admin = User.objects.create_user(
            email="cadmin@example.com",
            password=self.password,
            name="Committee Admin",
            role="committee_admin",
        )
        self.committee_admin.managed_conferences.add(self.conference)

        self.super_admin = User.objects.create_superuser(
            email="superadmin@example.com", password=self.password, name="Super"
        )

    def _login(self, user):
        self.client.login(username=user.email, password=self.password)

    def test_delegate_dashboard_requires_login(self):
        response = self.client.get(reverse("chits:delegate_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_delegate_can_reach_delegate_dashboard_after_committee_set(self):
        self._login(self.delegate)
        # simulate the dashboard_redirect flow that sets active_committee_id
        self.client.get(reverse("accounts:dashboard_redirect"))
        response = self.client.get(reverse("chits:delegate_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_eb_member_cannot_reach_delegate_dashboard(self):
        self._login(self.eb_member)
        session = self.client.session
        session["active_committee_id"] = str(self.committee.id)
        session.save()
        response = self.client.get(reverse("chits:delegate_dashboard"))
        # eb_member has zero active delegate standing anywhere, so the
        # role-wide check (DelegateRequiredMixin) rejects before the
        # per-committee check even runs.
        self.assertRedirects(response, reverse("accounts:unauthorized"))

    def test_delegate_cannot_reach_eb_dashboard(self):
        self._login(self.delegate)
        session = self.client.session
        session["active_committee_id"] = str(self.committee.id)
        session.save()
        response = self.client.get(reverse("chits:eb_dashboard"))
        # delegate has zero active EB standing anywhere.
        self.assertRedirects(response, reverse("accounts:unauthorized"))

    def test_user_with_no_assignment_is_redirected_to_unauthorized(self):
        self._login(self.plain_user)
        response = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(response, reverse("accounts:unauthorized"))

    def test_plain_user_cannot_access_admin_dashboard(self):
        self._login(self.plain_user)
        response = self.client.get(reverse("adminpanel:dashboard"))
        self.assertRedirects(response, reverse("accounts:unauthorized"))

    def test_committee_admin_can_reach_admin_dashboard(self):
        self._login(self.committee_admin)
        response = self.client.get(reverse("adminpanel:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_super_admin_can_reach_admin_dashboard(self):
        self._login(self.super_admin)
        response = self.client.get(reverse("adminpanel:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_redirect_sends_delegate_to_delegate_dashboard(self):
        self._login(self.delegate)
        response = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(response, reverse("chits:delegate_dashboard"))

    def test_dashboard_redirect_sends_eb_to_eb_dashboard(self):
        self._login(self.eb_member)
        response = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(response, reverse("chits:eb_dashboard"))

    def test_dashboard_redirect_sends_admin_to_admin_dashboard(self):
        self._login(self.committee_admin)
        response = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(response, reverse("adminpanel:dashboard"))

    def test_stale_session_committee_id_bounces_to_redirect(self):
        self._login(self.delegate)
        session = self.client.session
        session["active_committee_id"] = "00000000-0000-0000-0000-000000000000"
        session.save()
        response = self.client.get(reverse("chits:delegate_dashboard"))
        # dashboard_redirect itself issues another redirect (302), so don't
        # follow all the way to a 200 — just confirm we land there.
        self.assertRedirects(
            response,
            reverse("accounts:dashboard_redirect"),
            target_status_code=302,
        )

    def test_delegate_loses_dashboard_access_once_deactivated(self):
        self._login(self.delegate)
        self.client.get(reverse("accounts:dashboard_redirect"))
        assignment = CountryAssignment.objects.get(user=self.delegate)
        assignment.is_active = False
        assignment.save()
        response = self.client.get(reverse("chits:delegate_dashboard"))
        # No active delegate standing left anywhere -> unauthorized, not a
        # redirect loop back through dashboard_redirect.
        self.assertRedirects(response, reverse("accounts:unauthorized"))

    def test_mixed_role_user_active_committee_context_mismatch_bounces_to_redirect(self):
        # A user who IS a delegate somewhere, but whose *active* session
        # committee is one where they're EB, not a delegate: the role-wide
        # check passes (they're a delegate elsewhere) but the per-committee
        # ActiveCommitteeMixin check must still reject this specific view.
        committee_2 = Committee.objects.create(
            conference=self.conference, name="ECOSOC", abbreviation="ECOSOC"
        )
        CountryAssignment.objects.create(
            user=self.eb_member, committee=committee_2, country_name="Kenya", country_code="KEN"
        )
        self._login(self.eb_member)
        session = self.client.session
        session["active_committee_id"] = str(self.committee.id)  # eb_member is EB here
        session.save()
        response = self.client.get(reverse("chits:delegate_dashboard"))
        self.assertRedirects(
            response, reverse("accounts:dashboard_redirect"), target_status_code=302
        )
