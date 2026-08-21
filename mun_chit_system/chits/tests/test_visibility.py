from datetime import date

from django.test import TestCase

from accounts.models import User
from chits.models import Chit, RecipientType
from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference, Room


def make_conference():
    return Conference.objects.create(
        name="GIPE MUN 2026", year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 3)
    )


class ChitNumberingTests(TestCase):
    def setUp(self):
        self.conference = make_conference()
        self.room = Room.objects.create(conference=self.conference, name="Room A")
        self.committee = Committee.objects.create(
            conference=self.conference, name="UNSC", abbreviation="UNSC", room=self.room
        )
        self.sender = User.objects.create_user(
            email="sender@example.com", password="StrongPass123!", name="Sender"
        )

    def test_chit_number_is_generated_and_unique(self):
        chit1 = Chit.objects.create(
            conference=self.conference,
            committee=self.committee,
            room=self.room,
            sender=self.sender,
            recipient_type=RecipientType.EXECUTIVE_BOARD,
            message="Hello",
        )
        chit2 = Chit.objects.create(
            conference=self.conference,
            committee=self.committee,
            room=self.room,
            sender=self.sender,
            recipient_type=RecipientType.EXECUTIVE_BOARD,
            message="Hello again",
        )
        self.assertTrue(chit1.chit_number.startswith("MUN-2026-UNSC-"))
        self.assertNotEqual(chit1.chit_number, chit2.chit_number)

    def test_self_recipient_rejected_via_clean(self):
        assignment = CountryAssignment.objects.create(
            user=self.sender, committee=self.committee, country_name="India", country_code="IND"
        )
        chit = Chit(
            conference=self.conference,
            committee=self.committee,
            room=self.room,
            sender=self.sender,
            sender_country=assignment,
            recipient_country=assignment,
            recipient_type=RecipientType.DELEGATE,
            message="To myself",
        )
        with self.assertRaises(Exception):
            chit.full_clean()


class ChitVisibilityScenarioTests(TestCase):
    """
    Implements the required scenario:
    1 conference, 3 committees each with its own room, delegates in each,
    a chit sent within Committee A, and full visibility assertions across
    delegates, EB, and administrators.
    """

    def setUp(self):
        self.conference = make_conference()

        self.room_a = Room.objects.create(conference=self.conference, name="Room A")
        self.room_b = Room.objects.create(conference=self.conference, name="Room B")
        self.room_c = Room.objects.create(conference=self.conference, name="Room C")

        self.committee_a = Committee.objects.create(
            conference=self.conference, name="UNSC", abbreviation="UNSC", room=self.room_a
        )
        self.committee_b = Committee.objects.create(
            conference=self.conference, name="ECOSOC", abbreviation="ECOSOC", room=self.room_b
        )
        self.committee_c = Committee.objects.create(
            conference=self.conference, name="UNHRC", abbreviation="UNHRC", room=self.room_c
        )

        # Delegates: sender + recipient in committee A, one delegate each in B and C.
        self.sender_a = User.objects.create_user(
            email="sender_a@example.com", password="StrongPass123!", name="Sender A"
        )
        self.recipient_a = User.objects.create_user(
            email="recipient_a@example.com", password="StrongPass123!", name="Recipient A"
        )
        self.delegate_b = User.objects.create_user(
            email="delegate_b@example.com", password="StrongPass123!", name="Delegate B"
        )
        self.delegate_c = User.objects.create_user(
            email="delegate_c@example.com", password="StrongPass123!", name="Delegate C"
        )

        self.sender_country_a = CountryAssignment.objects.create(
            user=self.sender_a, committee=self.committee_a, country_name="India", country_code="IND"
        )
        self.recipient_country_a = CountryAssignment.objects.create(
            user=self.recipient_a, committee=self.committee_a, country_name="France", country_code="FRA"
        )
        CountryAssignment.objects.create(
            user=self.delegate_b, committee=self.committee_b, country_name="Brazil", country_code="BRA"
        )
        CountryAssignment.objects.create(
            user=self.delegate_c, committee=self.committee_c, country_name="Japan", country_code="JPN"
        )

        # EB members, one per committee.
        self.eb_a = User.objects.create_user(
            email="eb_a@example.com", password="StrongPass123!", name="EB A", role="executive_board"
        )
        self.eb_b = User.objects.create_user(
            email="eb_b@example.com", password="StrongPass123!", name="EB B", role="executive_board"
        )
        self.eb_c = User.objects.create_user(
            email="eb_c@example.com", password="StrongPass123!", name="EB C", role="executive_board"
        )
        CommitteeStaff.objects.create(
            user=self.eb_a, committee=self.committee_a, role=CommitteeStaff.StaffRole.CHAIR
        )
        CommitteeStaff.objects.create(
            user=self.eb_b, committee=self.committee_b, role=CommitteeStaff.StaffRole.CHAIR
        )
        CommitteeStaff.objects.create(
            user=self.eb_c, committee=self.committee_c, role=CommitteeStaff.StaffRole.CHAIR
        )

        # Administrator managing this conference.
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            name="Committee Admin",
            role="committee_admin",
        )
        self.admin.managed_conferences.add(self.conference)

        self.super_admin = User.objects.create_superuser(
            email="super2@example.com", password="StrongPass123!", name="Super"
        )

        # A chit sent from Committee A, delegate-to-delegate.
        self.chit_delegate = Chit.objects.create(
            conference=self.conference,
            committee=self.committee_a,
            room=self.room_a,
            sender=self.sender_a,
            sender_country=self.sender_country_a,
            recipient_country=self.recipient_country_a,
            recipient_type=RecipientType.DELEGATE,
            message="Delegate to delegate chit in Committee A",
            status="submitted",
        )

        # A chit addressed to the Executive Board of Committee A.
        self.chit_to_eb_a = Chit.objects.create(
            conference=self.conference,
            committee=self.committee_a,
            room=self.room_a,
            sender=self.sender_a,
            sender_country=self.sender_country_a,
            recipient_type=RecipientType.EXECUTIVE_BOARD,
            message="Point of order for the EB of Committee A",
            status="submitted",
        )

    def test_recipient_in_committee_a_can_see_delegate_chit(self):
        visible = Chit.objects.visible_to(self.recipient_a)
        self.assertIn(self.chit_delegate, visible)

    def test_sender_can_see_their_own_chit(self):
        visible = Chit.objects.visible_to(self.sender_a)
        self.assertIn(self.chit_delegate, visible)

    def test_committee_b_delegate_cannot_see_committee_a_chit(self):
        visible = Chit.objects.visible_to(self.delegate_b)
        self.assertNotIn(self.chit_delegate, visible)

    def test_committee_c_delegate_cannot_see_committee_a_chit(self):
        visible = Chit.objects.visible_to(self.delegate_c)
        self.assertNotIn(self.chit_delegate, visible)

    def test_eb_of_committee_a_can_see_eb_addressed_chit(self):
        visible = Chit.objects.visible_to(self.eb_a)
        self.assertIn(self.chit_to_eb_a, visible)

    def test_eb_of_committee_a_cannot_see_delegate_to_delegate_chit(self):
        # EB only sees chits explicitly addressed to the Executive Board.
        visible = Chit.objects.visible_to(self.eb_a)
        self.assertNotIn(self.chit_delegate, visible)

    def test_eb_of_committee_b_cannot_see_committee_a_eb_chit(self):
        visible = Chit.objects.visible_to(self.eb_b)
        self.assertNotIn(self.chit_to_eb_a, visible)

    def test_eb_of_committee_c_cannot_see_committee_a_eb_chit(self):
        visible = Chit.objects.visible_to(self.eb_c)
        self.assertNotIn(self.chit_to_eb_a, visible)

    def test_administrator_sees_all_chits_in_managed_conference(self):
        visible = Chit.objects.visible_to(self.admin)
        self.assertIn(self.chit_delegate, visible)
        self.assertIn(self.chit_to_eb_a, visible)

    def test_super_admin_sees_everything(self):
        visible = Chit.objects.visible_to(self.super_admin)
        self.assertIn(self.chit_delegate, visible)
        self.assertIn(self.chit_to_eb_a, visible)

    def test_unrelated_delegate_cannot_see_eb_chit(self):
        visible = Chit.objects.visible_to(self.delegate_b)
        self.assertNotIn(self.chit_to_eb_a, visible)
