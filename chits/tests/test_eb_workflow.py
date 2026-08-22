from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from chits.models import Category, Chit, ChitReply, RecipientType, Status
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
        self._make_eb_chit(status=Status.SUBMITTED)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"))
        self.assertEqual(response.context["queue_counts"]["new"], 3)

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
    """
    Reply permission has moved from the Executive Board to the delegate
    parties of a chit (see DelegateReplyTests below). EB members can no
    longer reply to anything — not even chits addressed directly to them
    — since there's no other party to grant reply to on those, and
    keeping a narrow EB-only exception would contradict "reply now
    belongs to delegates."
    """

    def test_eb_cannot_reply_to_eb_addressed_chit(self):
        chit = self._make_eb_chit()
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Noted, please raise this during the next session."},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)

    def test_delegate_cannot_reply_to_eb_addressed_chit(self):
        chit = self._make_eb_chit()
        self._login_and_activate(self.sender)  # sender is the chit's own sender
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "There's no recipient delegate to reply as here."},
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


class DelegateReplyTests(EBWorkflowTestBase):
    """
    Reply capability on a delegate-to-delegate chit belongs to the two
    delegates actually party to it — the sender and the addressed
    recipient country's delegate — regardless of whether it's marked
    Via EB. An unrelated delegate, and the EB, cannot reply.
    """

    def test_sender_can_reply(self):
        chit = self._make_delegate_chit()
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Following up on my earlier chit."},
        )
        self.assertRedirects(response, reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 1)
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.REPLIED)
        self.assertIsNotNone(chit.replied_at)

    def test_recipient_delegate_can_reply(self):
        chit = self._make_delegate_chit()
        self._login_and_activate(self.other_delegate)  # the recipient
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Responding to your chit."},
        )
        self.assertRedirects(response, reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 1)

    def test_reply_records_correct_author(self):
        chit = self._make_delegate_chit()
        self._login_and_activate(self.other_delegate)
        self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Reply text here."},
        )
        reply = ChitReply.objects.get(chit=chit)
        self.assertEqual(reply.author, self.other_delegate)

    def test_unrelated_delegate_cannot_reply(self):
        chit = self._make_delegate_chit()
        third_delegate = User.objects.create_user(
            email="third@example.com", password=self.password, name="Third Delegate"
        )
        CountryAssignment.objects.create(
            user=third_delegate, committee=self.committee, country_name="Kenya", country_code="KEN"
        )
        self._login_and_activate(third_delegate)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "I'm not part of this exchange."},
        )
        # visible_to() excludes it for an unrelated delegate entirely.
        self.assertEqual(response.status_code, 404)

    def test_eb_cannot_reply_to_ordinary_delegate_chit(self):
        chit = self._make_delegate_chit(is_via_eb=False)
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Should not be allowed."},
        )
        self.assertEqual(response.status_code, 404)  # not even visible to EB without Via EB

    def test_eb_cannot_reply_to_via_eb_chit(self):
        chit = self._make_delegate_chit(is_via_eb=True)
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "EB should no longer be able to do this."},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)

    def test_reply_disabled_by_conference_setting(self):
        self.conference.replies_enabled = False
        self.conference.save()
        chit = self._make_delegate_chit()
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Should be blocked."},
        )
        self.assertRedirects(response, reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)

    def test_cannot_reply_to_archived_chit(self):
        chit = self._make_delegate_chit(status=Status.ARCHIVED)
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Too late."},
        )
        self.assertRedirects(response, reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)

    def test_empty_reply_rejected(self):
        chit = self._make_delegate_chit()
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]), {"action": "reply", "message": ""}
        )
        self.assertEqual(ChitReply.objects.filter(chit=chit).count(), 0)

    def test_reply_visible_to_both_delegates_and_eb_if_via_eb(self):
        chit = self._make_delegate_chit(is_via_eb=True)
        self._login_and_activate(self.sender)
        self.client.post(
            reverse("chits:detail", args=[chit.public_id]),
            {"action": "reply", "message": "Visible to everyone on this thread."},
        )
        for viewer in (self.sender, self.other_delegate, self.eb_member):
            self._login_and_activate(viewer)
            response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
            self.assertContains(response, "Visible to everyone on this thread.")


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
        self._make_eb_chit(status=Status.SUBMITTED)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_dashboard"))
        self.assertEqual(response.context["new_count"], 3)


class ViaEBTests(EBWorkflowTestBase):
    """
    A delegate-to-delegate chit marked is_via_eb=True should become
    visible to (and repliable by) the EB of the SENDER's committee, in
    addition to the sender and the actual recipient delegate — without
    changing visibility for an ordinary (non-via-EB) delegate chit, or
    for EB members of a different committee.
    """

    def test_ordinary_delegate_chit_not_visible_to_eb(self):
        chit = self._make_delegate_chit(is_via_eb=False)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_via_eb_chit_visible_to_committee_eb(self):
        chit = self._make_delegate_chit(is_via_eb=True)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 200)

    def test_via_eb_chit_visible_to_recipient_delegate(self):
        chit = self._make_delegate_chit(is_via_eb=True)
        self._login_and_activate(self.other_delegate)  # the recipient
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 200)

    def test_via_eb_chit_not_visible_to_eb_of_different_committee(self):
        chit = self._make_delegate_chit(is_via_eb=True)
        self._login_and_activate(self.other_eb_member)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_via_eb_chit_appears_in_eb_incoming_inbox(self):
        chit = self._make_delegate_chit(is_via_eb=True)
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:eb_incoming"))
        self.assertIn(chit, list(response.context["chits"]))

    def test_eb_can_archive_via_eb_chit(self):
        chit = self._make_delegate_chit(is_via_eb=True)
        self._login_and_activate(self.eb_member)
        response = self.client.post(
            reverse("chits:detail", args=[chit.public_id]), {"action": "archive"}
        )
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.ARCHIVED)

    def test_via_eb_viewing_by_eb_does_not_mark_read_for_recipient(self):
        """
        The EB is a CC'd observer on a via-EB chit, not the actual
        addressee — their viewing it shouldn't fire the delegate
        recipient's read receipt.
        """
        chit = self._make_delegate_chit(is_via_eb=True, status=Status.SUBMITTED)
        self._login_and_activate(self.eb_member)
        self.client.get(reverse("chits:detail", args=[chit.public_id]))
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.SUBMITTED)

    def test_model_rejects_via_eb_on_eb_addressed_chit(self):
        chit = Chit(
            conference=self.conference,
            committee=self.committee,
            room=self.room,
            sender=self.sender,
            sender_country=self.sender_assignment,
            recipient_type=RecipientType.EXECUTIVE_BOARD,
            is_via_eb=True,
            message="Invalid combination.",
        )
        with self.assertRaises(Exception):
            chit.full_clean()

    def test_via_eb_compose_form_end_to_end(self):
        self._login_and_activate(self.sender)
        self.client.post(
            reverse("chits:send"),
            {
                "recipient_type": RecipientType.DELEGATE,
                "recipient_country": str(self.other_assignment.id),
                "is_via_eb": "on",
                "subject": "Compose flow test",
                "message": "Sent with Via EB checked.",
                "category": Category.OTHER,
                "agree_to_rules": "on",
            },
        )
        self.client.post(reverse("chits:preview"))
        chit = Chit.objects.get(subject="Compose flow test")
        self.assertTrue(chit.is_via_eb)

        # Confirm the EB genuinely gained visibility through the real
        # compose -> preview -> confirm flow, not just direct ORM creation.
        self._login_and_activate(self.eb_member)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 200)

    def test_via_eb_forced_false_when_sending_to_eb_directly(self):
        self._login_and_activate(self.sender)
        self.client.post(
            reverse("chits:send"),
            {
                "recipient_type": RecipientType.EXECUTIVE_BOARD,
                "is_via_eb": "on",  # should be ignored/forced off server-side
                "subject": "EB direct test",
                "message": "Sent directly to EB with Via EB also checked.",
                "category": Category.OTHER,
                "agree_to_rules": "on",
            },
        )
        self.client.post(reverse("chits:preview"))
        chit = Chit.objects.get(subject="EB direct test")
        self.assertFalse(chit.is_via_eb)
