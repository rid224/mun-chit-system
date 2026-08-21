from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference


class CommitteeConstraintTests(TestCase):
    def setUp(self):
        self.conference = Conference.objects.create(
            name="GIPE MUN 2026",
            year=2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 3),
        )

    def test_duplicate_committee_name_in_same_conference_rejected(self):
        Committee.objects.create(conference=self.conference, name="UNSC")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Committee.objects.create(conference=self.conference, name="UNSC")

    def test_same_name_allowed_across_different_conferences(self):
        other_conference = Conference.objects.create(
            name="Other MUN 2027",
            year=2027,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 9, 3),
        )
        Committee.objects.create(conference=self.conference, name="UNSC")
        # Should not raise
        Committee.objects.create(conference=other_conference, name="UNSC")


class CountryAssignmentConstraintTests(TestCase):
    def setUp(self):
        self.conference = Conference.objects.create(
            name="GIPE MUN 2026",
            year=2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 3),
        )
        self.committee = Committee.objects.create(conference=self.conference, name="UNSC")
        self.delegate1 = User.objects.create_user(
            email="d1@example.com", password="StrongPass123!", name="Delegate One"
        )
        self.delegate2 = User.objects.create_user(
            email="d2@example.com", password="StrongPass123!", name="Delegate Two"
        )

    def test_two_active_delegates_same_country_same_committee_rejected(self):
        CountryAssignment.objects.create(
            user=self.delegate1, committee=self.committee, country_name="India", country_code="IND"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CountryAssignment.objects.create(
                    user=self.delegate2,
                    committee=self.committee,
                    country_name="India",
                    country_code="IND",
                )

    def test_inactive_assignment_does_not_block_new_active_one(self):
        first = CountryAssignment.objects.create(
            user=self.delegate1, committee=self.committee, country_name="India", country_code="IND"
        )
        first.is_active = False
        first.save()
        # Should not raise, since the prior assignment is now inactive.
        CountryAssignment.objects.create(
            user=self.delegate2, committee=self.committee, country_name="India", country_code="IND"
        )

    def test_same_delegate_can_hold_different_country_in_different_committee(self):
        committee_b = Committee.objects.create(conference=self.conference, name="ECOSOC")
        CountryAssignment.objects.create(
            user=self.delegate1, committee=self.committee, country_name="India", country_code="IND"
        )
        # Same user, different committee, different country — should not raise.
        CountryAssignment.objects.create(
            user=self.delegate1, committee=committee_b, country_name="France", country_code="FRA"
        )


class CommitteeStaffConstraintTests(TestCase):
    def setUp(self):
        self.conference = Conference.objects.create(
            name="GIPE MUN 2026",
            year=2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 3),
        )
        self.committee = Committee.objects.create(conference=self.conference, name="UNSC")
        self.eb_user = User.objects.create_user(
            email="eb@example.com", password="StrongPass123!", name="EB One", role="executive_board"
        )

    def test_duplicate_staff_role_for_same_user_committee_rejected(self):
        CommitteeStaff.objects.create(
            user=self.eb_user, committee=self.committee, role=CommitteeStaff.StaffRole.CHAIR
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CommitteeStaff.objects.create(
                    user=self.eb_user,
                    committee=self.committee,
                    role=CommitteeStaff.StaffRole.VICE_CHAIR,
                )
