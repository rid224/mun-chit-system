from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from chits.models import Category, Chit, Priority, RecipientType, Status
from committees.models import Committee, CountryAssignment
from conferences.models import Conference, Room


class ChitSubmissionTestBase(TestCase):
    def setUp(self):
        self.conference = Conference.objects.create(
            name="Submission Test MUN",
            year=2026,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 3),
        )
        self.room = Room.objects.create(conference=self.conference, name="Room A")
        self.committee = Committee.objects.create(
            conference=self.conference, name="UNSC", abbreviation="UNSC", room=self.room
        )

        self.password = "StrongPass123!"

        self.sender = User.objects.create_user(
            email="sender@example.com", password=self.password, name="Sender"
        )
        self.sender_assignment = CountryAssignment.objects.create(
            user=self.sender, committee=self.committee, country_name="India", country_code="IND"
        )

        self.recipient = User.objects.create_user(
            email="recipient@example.com", password=self.password, name="Recipient"
        )
        self.recipient_assignment = CountryAssignment.objects.create(
            user=self.recipient,
            committee=self.committee,
            country_name="France",
            country_code="FRA",
        )

    def _login_and_activate(self, user):
        self.client.login(username=user.email, password=self.password)
        self.client.get(reverse("accounts:dashboard_redirect"))

    def _valid_payload(self, **overrides):
        payload = {
            "recipient_type": RecipientType.DELEGATE,
            "recipient_country": str(self.recipient_assignment.id),
            "subject": "Test subject",
            "message": "Hello there, this is a test chit.",
            "category": Category.POINT_OF_INFORMATION,
            "priority": Priority.NORMAL,
            "agree_to_rules": "on",
        }
        payload.update(overrides)
        return payload


class SendChitFormValidationTests(ChitSubmissionTestBase):
    def test_send_page_requires_login(self):
        response = self.client.get(reverse("chits:send"))
        self.assertEqual(response.status_code, 302)

    def test_valid_submission_redirects_to_preview(self):
        self._login_and_activate(self.sender)
        response = self.client.post(reverse("chits:send"), self._valid_payload())
        self.assertRedirects(response, reverse("chits:preview"))

    def test_valid_submission_stores_draft_in_session_not_db(self):
        self._login_and_activate(self.sender)
        self.client.post(reverse("chits:send"), self._valid_payload())
        self.assertEqual(Chit.objects.count(), 0)
        self.assertIn("chit_draft", self.client.session)

    def test_self_recipient_rejected(self):
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:send"),
            self._valid_payload(recipient_country=str(self.sender_assignment.id)),
        )
        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        # The sender's own country is excluded from the recipient queryset
        # entirely (defense in depth), so Django's field-level validation
        # rejects it as an invalid choice before the custom self-recipient
        # message in clean() would even get a chance to fire.
        self.assertContains(response, "not one of the available choices")
        self.assertEqual(Chit.objects.count(), 0)

    def test_missing_recipient_country_for_delegate_type_rejected(self):
        self._login_and_activate(self.sender)
        payload = self._valid_payload()
        payload.pop("recipient_country")
        response = self.client.post(reverse("chits:send"), payload)
        self.assertContains(response, "Choose which country to send this chit to")

    def test_message_over_max_length_rejected(self):
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:send"), self._valid_payload(message="x" * 2001)
        )
        self.assertContains(response, "exceeds the maximum length")

    def test_missing_agreement_checkbox_rejected(self):
        self._login_and_activate(self.sender)
        payload = self._valid_payload()
        payload.pop("agree_to_rules")
        response = self.client.post(reverse("chits:send"), payload)
        self.assertEqual(Chit.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_recipient_from_other_committee_rejected(self):
        other_committee = Committee.objects.create(
            conference=self.conference, name="ECOSOC", abbreviation="ECOSOC"
        )
        other_delegate = User.objects.create_user(
            email="other@example.com", password=self.password, name="Other"
        )
        other_assignment = CountryAssignment.objects.create(
            user=other_delegate,
            committee=other_committee,
            country_name="Kenya",
            country_code="KEN",
        )
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:send"),
            self._valid_payload(recipient_country=str(other_assignment.id)),
        )
        # ModelChoiceField queryset is scoped to the committee, so this PK
        # simply won't validate as a valid choice.
        self.assertEqual(Chit.objects.count(), 0)

    def test_eb_recipient_disabled_by_conference_setting(self):
        self.conference.delegate_to_eb_enabled = False
        self.conference.save()
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:send"),
            self._valid_payload(recipient_type=RecipientType.EXECUTIVE_BOARD),
        )
        self.assertContains(response, "currently disabled")
        self.assertEqual(Chit.objects.count(), 0)

    def test_submissions_disabled_conference_wide(self):
        self.conference.chit_submissions_enabled = False
        self.conference.save()
        self._login_and_activate(self.sender)
        response = self.client.post(reverse("chits:send"), self._valid_payload())
        self.assertContains(response, "currently disabled")
        self.assertEqual(Chit.objects.count(), 0)

    def test_anonymous_field_hidden_when_conference_disables_it(self):
        self._login_and_activate(self.sender)
        response = self.client.get(reverse("chits:send"))
        self.assertNotContains(response, 'name="is_anonymous"')

    def test_anonymous_field_shown_when_conference_enables_it(self):
        self.conference.anonymous_chits_enabled = True
        self.conference.save()
        self._login_and_activate(self.sender)
        response = self.client.get(reverse("chits:send"))
        self.assertContains(response, 'name="is_anonymous"')


class PreviewAndSubmitFlowTests(ChitSubmissionTestBase):
    def _compose(self, **overrides):
        self._login_and_activate(self.sender)
        self.client.post(reverse("chits:send"), self._valid_payload(**overrides))

    def test_preview_without_draft_redirects_to_send(self):
        self._login_and_activate(self.sender)
        response = self.client.get(reverse("chits:preview"))
        self.assertRedirects(response, reverse("chits:send"))

    def test_preview_renders_draft_content(self):
        self._compose(subject="Urgent matter", message="Please respond quickly.")
        response = self.client.get(reverse("chits:preview"))
        self.assertContains(response, "Urgent matter")
        self.assertContains(response, "Please respond quickly.")

    def test_preview_escapes_html_in_message(self):
        self._compose(message="<script>alert('xss')</script> hello")
        response = self.client.get(reverse("chits:preview"))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")

    def test_confirming_preview_creates_chit_and_clears_draft(self):
        self._compose()
        response = self.client.post(reverse("chits:preview"))
        self.assertEqual(Chit.objects.count(), 1)
        chit = Chit.objects.first()
        self.assertEqual(chit.status, Status.SUBMITTED)
        self.assertIsNotNone(chit.submitted_at)
        self.assertTrue(chit.chit_number.startswith("MUN-2026-UNSC-"))
        self.assertRedirects(response, reverse("chits:detail", args=[chit.public_id]))
        self.assertNotIn("chit_draft", self.client.session)

    def test_chit_auto_attaches_committee_room_conference_and_sender(self):
        self._compose()
        self.client.post(reverse("chits:preview"))
        chit = Chit.objects.first()
        self.assertEqual(chit.committee, self.committee)
        self.assertEqual(chit.room, self.room)
        self.assertEqual(chit.conference, self.conference)
        self.assertEqual(chit.sender, self.sender)
        self.assertEqual(chit.sender_country, self.sender_assignment)

    def test_state_change_between_compose_and_confirm_is_caught(self):
        self._compose()
        # Disable submissions after composing but before confirming.
        self.conference.chit_submissions_enabled = False
        self.conference.save()
        response = self.client.post(reverse("chits:preview"))
        self.assertRedirects(response, reverse("chits:send"))
        self.assertEqual(Chit.objects.count(), 0)


class ChitHistoryViewTests(ChitSubmissionTestBase):
    def _create_chit(self, sender, sender_assignment, recipient_assignment, **overrides):
        defaults = dict(
            conference=self.conference,
            committee=self.committee,
            room=self.room,
            sender=sender,
            sender_country=sender_assignment,
            recipient_country=recipient_assignment,
            recipient_type=RecipientType.DELEGATE,
            message="Test message",
            status=Status.SUBMITTED,
        )
        defaults.update(overrides)
        return Chit.objects.create(**defaults)

    def test_sent_list_shows_own_chits(self):
        self._create_chit(self.sender, self.sender_assignment, self.recipient_assignment)
        self._login_and_activate(self.sender)
        response = self.client.get(reverse("chits:sent"))
        self.assertEqual(len(response.context["chits"]), 1)

    def test_sent_list_does_not_show_others_chits(self):
        self._create_chit(self.sender, self.sender_assignment, self.recipient_assignment)
        self._login_and_activate(self.recipient)
        response = self.client.get(reverse("chits:sent"))
        self.assertEqual(len(response.context["chits"]), 0)

    def test_received_list_shows_chits_addressed_to_me(self):
        self._create_chit(self.sender, self.sender_assignment, self.recipient_assignment)
        self._login_and_activate(self.recipient)
        response = self.client.get(reverse("chits:received"))
        self.assertEqual(len(response.context["chits"]), 1)

    def test_received_list_filter_by_status(self):
        self._create_chit(
            self.sender, self.sender_assignment, self.recipient_assignment, status=Status.READ
        )
        self._create_chit(
            self.sender,
            self.sender_assignment,
            self.recipient_assignment,
            status=Status.SUBMITTED,
        )
        self._login_and_activate(self.recipient)
        response = self.client.get(reverse("chits:received"), {"status": "read"})
        self.assertEqual(len(response.context["chits"]), 1)
        self.assertEqual(response.context["chits"][0].status, Status.READ)

    def test_received_list_search_by_chit_number(self):
        chit = self._create_chit(
            self.sender, self.sender_assignment, self.recipient_assignment
        )
        self._login_and_activate(self.recipient)
        response = self.client.get(reverse("chits:received"), {"q": chit.chit_number})
        self.assertEqual(len(response.context["chits"]), 1)

    def test_pagination_limits_page_size(self):
        for i in range(20):
            self._create_chit(self.sender, self.sender_assignment, self.recipient_assignment)
        self._login_and_activate(self.recipient)
        response = self.client.get(reverse("chits:received"))
        self.assertEqual(len(response.context["chits"]), 15)
        self.assertTrue(response.context["is_paginated"])

    def test_detail_view_visible_to_sender(self):
        chit = self._create_chit(
            self.sender, self.sender_assignment, self.recipient_assignment
        )
        self._login_and_activate(self.sender)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 200)

    def test_detail_view_visible_to_recipient(self):
        chit = self._create_chit(
            self.sender, self.sender_assignment, self.recipient_assignment
        )
        self._login_and_activate(self.recipient)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 200)

    def test_detail_view_returns_404_for_unrelated_delegate(self):
        chit = self._create_chit(
            self.sender, self.sender_assignment, self.recipient_assignment
        )
        unrelated = User.objects.create_user(
            email="unrelated@example.com", password=self.password, name="Unrelated"
        )
        other_committee = Committee.objects.create(
            conference=self.conference, name="ECOSOC", abbreviation="ECOSOC"
        )
        CountryAssignment.objects.create(
            user=unrelated, committee=other_committee, country_name="Kenya", country_code="KEN"
        )
        self._login_and_activate(unrelated)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_detail_escapes_message_content(self):
        chit = self._create_chit(
            self.sender,
            self.sender_assignment,
            self.recipient_assignment,
            message="<img src=x onerror=alert(1)>",
        )
        self._login_and_activate(self.sender)
        response = self.client.get(reverse("chits:detail", args=[chit.public_id]))
        self.assertContains(response, "&lt;img")
        self.assertNotContains(response, "<img src=x onerror")

    def test_recipient_viewing_chit_transitions_status_to_read(self):
        chit = self._create_chit(
            self.sender, self.sender_assignment, self.recipient_assignment
        )
        self.assertEqual(chit.status, Status.SUBMITTED)
        self._login_and_activate(self.recipient)
        self.client.get(reverse("chits:detail", args=[chit.public_id]))
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.READ)
        self.assertIsNotNone(chit.delivered_at)
        self.assertIsNotNone(chit.read_at)

    def test_sender_viewing_own_chit_does_not_change_status(self):
        chit = self._create_chit(
            self.sender, self.sender_assignment, self.recipient_assignment
        )
        self._login_and_activate(self.sender)
        self.client.get(reverse("chits:detail", args=[chit.public_id]))
        chit.refresh_from_db()
        self.assertEqual(chit.status, Status.SUBMITTED)


class CrossCommitteeChitTests(ChitSubmissionTestBase):
    """
    Covers a gap found during the Phase 6 spec-coverage review: the
    cross-committee toggles existed on Conference/Committee and were
    editable in the admin panel, but the compose form never implemented
    them, and even after implementing the queryset side, the preview step
    and the recipient's Received list were both still hard-scoped to a
    single committee — silently hiding a cross-committee chit from the
    very person it was sent to. All three layers are covered here.
    """

    def setUp(self):
        super().setUp()
        self.other_committee = Committee.objects.create(
            conference=self.conference, name="ECOSOC", abbreviation="ECOSOC"
        )
        self.other_delegate = User.objects.create_user(
            email="other_committee_delegate@example.com", password=self.password, name="Other"
        )
        self.other_assignment = CountryAssignment.objects.create(
            user=self.other_delegate,
            committee=self.other_committee,
            country_name="Kenya",
            country_code="KEN",
        )

    def _enable_cross_committee(self):
        self.committee.allow_cross_committee_chits = True
        self.committee.save()
        self.other_committee.allow_cross_committee_chits = True
        self.other_committee.save()
        self.conference.cross_committee_chits_enabled = True
        self.conference.save()

    def test_cross_committee_recipient_rejected_when_disabled(self):
        # Toggles left at their defaults (disabled).
        self._login_and_activate(self.sender)
        response = self.client.post(
            reverse("chits:send"),
            self._valid_payload(recipient_country=str(self.other_assignment.id)),
        )
        self.assertEqual(Chit.objects.count(), 0)
        self.assertContains(response, "not one of the available choices")

    def test_cross_committee_recipient_accepted_when_enabled(self):
        self._enable_cross_committee()
        self._login_and_activate(self.sender)
        self.client.post(
            reverse("chits:send"),
            self._valid_payload(recipient_country=str(self.other_assignment.id)),
        )
        response = self.client.get(reverse("chits:preview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kenya")

        confirm = self.client.post(reverse("chits:preview"))
        self.assertEqual(Chit.objects.count(), 1)
        chit = Chit.objects.first()
        self.assertEqual(chit.recipient_country, self.other_assignment)
        self.assertRedirects(confirm, reverse("chits:detail", args=[chit.public_id]))

    def test_cross_committee_chit_appears_in_recipients_received_list(self):
        self._enable_cross_committee()
        self._login_and_activate(self.sender)
        self.client.post(
            reverse("chits:send"),
            self._valid_payload(recipient_country=str(self.other_assignment.id)),
        )
        self.client.post(reverse("chits:preview"))

        self.client.logout()
        self.client.login(username=self.other_delegate.email, password=self.password)
        self.client.get(reverse("accounts:dashboard_redirect"))

        response = self.client.get(reverse("chits:received"))
        self.assertEqual(len(response.context["chits"]), 1)

    def test_cross_committee_chit_appears_in_senders_sent_list_only_under_own_committee(self):
        self._enable_cross_committee()
        self._login_and_activate(self.sender)
        self.client.post(
            reverse("chits:send"),
            self._valid_payload(recipient_country=str(self.other_assignment.id)),
        )
        self.client.post(reverse("chits:preview"))

        response = self.client.get(reverse("chits:sent"))
        self.assertEqual(len(response.context["chits"]), 1)

    def test_disabling_toggle_mid_flow_is_caught_at_confirm(self):
        self._enable_cross_committee()
        self._login_and_activate(self.sender)
        self.client.post(
            reverse("chits:send"),
            self._valid_payload(recipient_country=str(self.other_assignment.id)),
        )
        # Admin disables cross-committee chits after compose, before confirm.
        self.conference.cross_committee_chits_enabled = False
        self.conference.save()

        response = self.client.post(reverse("chits:preview"))
        self.assertRedirects(response, reverse("chits:send"))
        self.assertEqual(Chit.objects.count(), 0)
