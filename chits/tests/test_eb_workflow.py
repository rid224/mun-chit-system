from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from chits.models import Category, Chit, ChitReply, Priority, RecipientType, Status
from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference, Room


class EBWorkflowTestBase(TestCase):
    def setUp(self):
        self.conference = Conference.objects.create(
            name="EB Test MUN", year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 3)
        )
        self.room = Room.objects.create(conference=self.conference, name="Room A")
        self.committee = Committee.objects.create(
            conference=self.conference, name="UNSC", abbreviation="UNSC", room=self.room
        )
        self.other_committee = Committee.objects.create(
            conference=self.conference, name="ECOSOC", abbreviation="ECOSOC"
        )

        self.password = "StrongPass123!"

        self.eb_member = User.objects.create_user(
            email="eb@example.com", password=self.password, name="EB Chair", role="executive_board"
        )
        CommitteeStaff.objects.create(
            user=self.eb_member, committee=self.committee, role=CommitteeStaff.StaffRole.CHAIR
        )

        self.other_eb_member = User.objects.create_user(
            email="other_eb@example.com",
            password=self.password,
            name="Other EB",
            role="executive_board",
        )
        CommitteeStaff.objects.create(
            user=self.other_eb_member,
            committee=self.other_committee,
            role=CommitteeStaff.StaffRole.CHAIR,
        )

        self.sender = User.objects.create_user(
            email="sender@example.com", password=self.password, name="Sender"
        )
        self.sender_assignment = CountryAssignment.objects.create(
            user=self.sender, committee=self.committee, country_name="India", country_code="IND"
        )
        self.other_delegate = User.objects.create_user(
            email="delegate2@example.com", password=self.password, name="Delegate2"
        )
        self.other_assignment = CountryAssignment.objects.create(
            user=self.other_delegate,
            committee=self.committee,
            country_name="France",
            country_code="FRA",
        )

    def _login_and_activate(self, user):
        self.client.login(username=user.email, password=self.password)
        self.client.get(reverse("accounts:dashboard_redirect"))

    def _make_eb_chit(self, **overrides):
        defaults = dict(
            conference=self.conference,
            committee=self.committee,
            room=self.room,
            sender=self.sender,
            sender_country=self.sender_assignment,
            recipient_type=RecipientType.EXECUTIVE_BOARD,
            message="Point of order",
            category=Category.PROCEDURAL_QUESTION,
            priority=Priority.NORMAL,
            status=Status.SUBMITTED,
        )
        defaults.update(overrides)
        return Chit.objects.create(**defaults)

    def _make_delegate_chit(self, **overrides):
        defaults = dict(
            conference=self.conference,
            committee=self.committee,
            room=self.room,
            sender=self.sender,
            sender_country=self.sender_assignment,
            recipient_country=self.other_assignment,
            recipient_type=RecipientType.DELEGATE,
            message="Delegate to delegate",
            status=Status.SUBMITTED,
        )
        defaults.update(overrides)
        return Chit.objects.create(**defaults)


class EBIncomingQueueTests(EBWorkflowTestBase):
    def test_eb_incoming_requires_eb_standing(self):
        self._login_and_activate(self.sender)
        response = self.client.get(reverse("chits:eb_incoming"))
        self.assertRedirects(response, reverse("accounts:unauthorized"))

    def test_eb_sees_only_eb_addressed_chits_in_own_committee(self):
        eb_chit = self._make_eb_chit()
        delegate_chit = self._make_delegate_chit()
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"))
        chits = list(response.context["chits"])
        self.assertIn(eb_chit, chits)
        self.assertNotIn(delegate_chit, chits)

    def test_eb_of_other_committee_does_not_see_this_committees_chits(self):
        eb_chit = self._make_eb_chit()
        self._login_and_activate(self.other_eb_member)
        response = self.client.get(reverse("chits:eb_incoming"))
        self.assertNotIn(eb_chit, list(response.context["chits"]))

    def test_new_queue_filters_to_submitted_only(self):
        new_chit = self._make_eb_chit(status=Status.SUBMITTED)
        read_chit = self._make_eb_chit(status=Status.READ)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"), {"queue": "new"})
        chits = list(response.context["chits"])
        self.assertIn(new_chit, chits)
        self.assertNotIn(read_chit, chits)

    def test_urgent_queue_filters_to_urgent_only(self):
        urgent_chit = self._make_eb_chit(priority=Priority.URGENT)
        normal_chit = self._make_eb_chit(priority=Priority.NORMAL)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"), {"queue": "urgent"})
        chits = list(response.context["chits"])
        self.assertIn(urgent_chit, chits)
        self.assertNotIn(normal_chit, chits)

    def test_awaiting_queue_filters_to_delivered_and_read(self):
        awaiting = self._make_eb_chit(status=Status.DELIVERED)
        submitted = self._make_eb_chit(status=Status.SUBMITTED)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"), {"queue": "awaiting"})
        chits = list(response.context["chits"])
        self.assertIn(awaiting, chits)
        self.assertNotIn(submitted, chits)

    def test_archived_chits_excluded_from_incoming(self):
        archived = self._make_eb_chit(status=Status.ARCHIVED)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"))
        self.assertNotIn(archived, list(response.context["chits"]))

    def test_queue_counts_reflect_committee_scope(self):
        self._make_eb_chit(status=Status.SUBMITTED)
        self._make_eb_chit(status=Status.SUBMITTED)
        self._make_eb_chit(priority=Priority.URGENT)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"))
        self.assertEqual(response.context["queue_counts"]["new"], 3)
        self.assertEqual(response.context["queue_counts"]["urgent"], 1)

    def test_search_by_subject(self):
        self._make_eb_chit(subject="Budget question")
        self._make_eb_chit(subject="Motion to adjourn")
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"), {"q": "Budget"})
        self.assertEqual(len(response.context["chits"]), 1)


class EBViewingMarksReadTests(EBWorkflowTestBase):
    def test_eb_viewing_chit_transitions_to_delivered_then_read(self):
        chit = self._make_eb_chit(status=Status.SUBMITTED)
        self._login_and_activate(self.eb_member)
        self.client.get(reverse("chits:detail", args=[chit.public_id]))
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.READ)
        self.assertIsNotNone(chit.delivered_at)
        self.assertIsNotNone(chit.read_at)

    def test_unrelated_eb_viewing_does_not_mark_read(self):
        chit = self._make_eb_chit(status=Status.SUBMITTED)
        # other_eb_member has no standing in `self.committee`, so
        # visible_to() should exclude this chit entirely (404), and
        # certainly must never mark it read.
        self._login_and_activate(self.other_eb_member)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 404)
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.SUBMITTED)

    def test_delegate_to_delegate_chit_not_affected_by_eb_view_logic(self):
        chit = self._make_delegate_chit(status=Status.SUBMITTED)
        # EB member has no reason to see a pure delegate-to-delegate chit,
        # and visible_to() should exclude it (404).
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 404)


class EBReplyTests(EBWorkflowTestBase):
    def test_eb_can_reply_to_eb_addressed_chit(self):
        chit = self._make_eb_chit()
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Noted, please raise this during the next session."},
        )
        self.assertRedirects(response, reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 1)
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.REPLIED)
        self.assertIsNotNone(chit.replied_at)

    def test_reply_records_correct_author(self):
        chit = self._make_eb_chit()
        self._login_and_activate(self.eb_member)
        self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Reply text here."},
        )
        reply = ChitReply.objects.get(chit=chit)
        self.assertEqual(reply.author, self.eb_member)

    def test_delegate_cannot_reply_to_eb_addressed_chit(self):
        chit = self._make_eb_chit()
        self._login_and_activate(self.sender)  # sender is the chit's own sender
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "I should not be able to do this."},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)

    def test_eb_of_different_committee_cannot_reply(self):
        chit = self._make_eb_chit()
        self._login_and_activate(self.other_eb_member)
        # visible_to() excludes it entirely for an unrelated EB member.
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Should not work."},
        )
        self.assertEqual(response.status_code, 404)

    def test_reply_disabled_by_conference_setting(self):
        self.conference.replies_enabled = False
        self.conference.save()
        chit = self._make_eb_chit()
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Should be blocked."},
        )
        self.assertRedirects(response, reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)

    def test_cannot_reply_to_archived_chit(self):
        chit = self._make_eb_chit(status=Status.ARCHIVED)
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Too late."},
        )
        self.assertRedirects(response, reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)

    def test_empty_reply_rejected(self):
        chit = self._make_eb_chit()
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]), {"action": "reply", "message": ""}
        )
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)


class EBArchiveTests(EBWorkflowTestBase):
    def test_eb_can_archive_eb_addressed_chit(self):
        chit = self._make_eb_chit(status=Status.READ)
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]), {"action": "archive"}
        )
        self.assertRedirects(response, reverse("chits:eb_incoming"))
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.ARCHIVED)
        self.assertIsNotNone(chit.archived_at)

    def test_archived_chit_appears_in_archive_view(self):
        chit = self._make_eb_chit(status=Status.ARCHIVED, archived_at=None)
        chit.archived_at = chit.created_at
        chit.save(update_fields=["archived_at"])
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_archive"))
        self.assertIn(chit, list(response.context["chits"]))

    def test_delegate_cannot_archive_chit(self):
        chit = self._make_eb_chit()
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]), {"action": "archive"}
        )
        self.assertEqual(response.status_code, 403)
        chit.refresh_from_db()
        self.assertNotEqual(chit.status, Status.ARCHIVED)


class EBDashboardCountTests(EBWorkflowTestBase):
    def test_dashboard_counts_scoped_to_committee_and_exclude_archived(self):
        self._make_eb_chit(status=Status.SUBMITTED)
        self._make_eb_chit(status=Status.SUBMITTED)
        self._make_eb_chit(status=Status.ARCHIVED)
        self._make_eb_chit(priority=Priority.URGENT)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_dashboard"))
        self.assertEqual(response.context["new_count"], 3)
        self.assertEqual(response.context["urgent_count"], 1)
