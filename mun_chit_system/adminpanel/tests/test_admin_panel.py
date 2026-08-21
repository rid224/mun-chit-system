import csv
import io
from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from audit.models import AuditLog
from chits.models import Chit, RecipientType, Status
from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference, Room


class AdminPanelTestBase(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"

        self.conference = Conference.objects.create(
            name="Admin Test MUN",
            year=2026,
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 3),
        )
        self.other_conference = Conference.objects.create(
            name="Other Admin Test MUN",
            year=2026,
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 3),
        )
        self.room = Room.objects.create(conference=self.conference, name="Room A")
        self.committee = Committee.objects.create(
            conference=self.conference, name="UNSC", abbreviation="UNSC", room=self.room
        )

        self.committee_admin = User.objects.create_user(
            email="commadmin@example.com",
            password=self.password,
            name="Comm Admin",
            role="committee_admin",
        )
        self.committee_admin.managed_conferences.add(self.conference)

        self.super_admin = User.objects.create_superuser(
            email="superadmin@example.com", password=self.password, name="Super Admin"
        )

        self.delegate = User.objects.create_user(
            email="delegate@example.com", password=self.password, name="A Delegate"
        )
        self.delegate_assignment = CountryAssignment.objects.create(
            user=self.delegate, committee=self.committee, country_name="India", country_code="IND"
        )

    def _login(self, user):
        self.client.login(username=user.email, password=self.password)


class AdminAccessControlTests(AdminPanelTestBase):
    def test_committee_admin_can_view_own_conference(self):
        self._login(self.committee_admin)
        response = self.client.get(
            reverse("adminpanel:conference_detail", args=[self.conference.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_committee_admin_cannot_view_unmanaged_conference(self):
        self._login(self.committee_admin)
        response = self.client.get(
            reverse("adminpanel:conference_detail", args=[self.other_conference.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_super_admin_can_view_any_conference(self):
        self._login(self.super_admin)
        response = self.client.get(
            reverse("adminpanel:conference_detail", args=[self.other_conference.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_delegate_cannot_reach_admin_panel(self):
        self._login(self.delegate)
        response = self.client.get(reverse("adminpanel:dashboard"))
        self.assertRedirects(response, reverse("accounts:unauthorized"))

    def test_only_super_admin_can_create_conference(self):
        self._login(self.committee_admin)
        response = self.client.get(reverse("adminpanel:conference_create"))
        self.assertRedirects(response, reverse("accounts:unauthorized"))

        self._login(self.super_admin)
        response = self.client.get(reverse("adminpanel:conference_create"))
        self.assertEqual(response.status_code, 200)

    def test_only_super_admin_can_view_audit_log(self):
        self._login(self.committee_admin)
        response = self.client.get(reverse("adminpanel:audit_log"))
        self.assertRedirects(response, reverse("accounts:unauthorized"))

        self._login(self.super_admin)
        response = self.client.get(reverse("adminpanel:audit_log"))
        self.assertEqual(response.status_code, 200)

    def test_committee_admin_cannot_edit_unmanaged_committee(self):
        other_committee = Committee.objects.create(
            conference=self.other_conference, name="ECOSOC", abbreviation="ECOSOC"
        )
        self._login(self.committee_admin)
        response = self.client.get(reverse("adminpanel:committee_detail", args=[other_committee.pk]))
        self.assertEqual(response.status_code, 403)

    def test_conference_list_scoped_to_managed_conferences(self):
        self._login(self.committee_admin)
        response = self.client.get(reverse("adminpanel:conference_list"))
        conferences = list(response.context["conferences"])
        self.assertIn(self.conference, conferences)
        self.assertNotIn(self.other_conference, conferences)


class ConferenceCRUDTests(AdminPanelTestBase):
    def test_super_admin_creates_conference(self):
        self._login(self.super_admin)
        response = self.client.post(
            reverse("adminpanel:conference_create"),
            {
                "name": "Newly Created MUN",
                "year": 2027,
                "venue": "",
                "start_date": "2027-01-01",
                "end_date": "2027-01-03",
                "timezone": "UTC",
                "is_active": "on",
            },
        )
        self.assertTrue(Conference.objects.filter(name="Newly Created MUN").exists())
        conference = Conference.objects.get(name="Newly Created MUN")
        self.assertRedirects(
            response, reverse("adminpanel:conference_detail", args=[conference.pk])
        )

    def test_committee_admin_edits_own_conference(self):
        self._login(self.committee_admin)
        response = self.client.post(
            reverse("adminpanel:conference_edit", args=[self.conference.pk]),
            {
                "name": "Renamed MUN",
                "year": 2026,
                "venue": "New venue",
                "start_date": "2026-11-01",
                "end_date": "2026-11-03",
                "timezone": "UTC",
                "is_active": "on",
            },
        )
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.name, "Renamed MUN")
        self.assertRedirects(
            response, reverse("adminpanel:conference_detail", args=[self.conference.pk])
        )

    def test_conference_settings_toggle(self):
        self._login(self.committee_admin)
        response = self.client.post(
            reverse("adminpanel:conference_settings", args=[self.conference.pk]),
            {
                "max_message_length": 1000,
                "chit_submissions_enabled": "on",
                "anonymous_chits_enabled": "on",
            },
        )
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.max_message_length, 1000)
        self.assertTrue(self.conference.anonymous_chits_enabled)
        # Unchecked boxes correctly become False (standard HTML checkbox semantics).
        self.assertFalse(self.conference.delegate_to_eb_enabled)
        self.assertRedirects(
            response, reverse("adminpanel:conference_detail", args=[self.conference.pk])
        )

    def test_settings_reject_message_length_over_2000(self):
        self._login(self.committee_admin)
        response = self.client.post(
            reverse("adminpanel:conference_settings", args=[self.conference.pk]),
            {"max_message_length": 5000},
        )
        self.assertContains(response, "between 1 and 2000")
        self.conference.refresh_from_db()
        self.assertEqual(self.conference.max_message_length, 2000)  # unchanged default

    def test_room_create_and_edit(self):
        self._login(self.committee_admin)
        create_url = reverse("adminpanel:room_create", args=[self.conference.pk])
        response = self.client.post(
            create_url, {"name": "Room B", "location": "", "is_active": "on"}
        )
        room = Room.objects.get(name="Room B", conference=self.conference)
        self.assertRedirects(
            response, reverse("adminpanel:conference_detail", args=[self.conference.pk])
        )

        edit_url = reverse("adminpanel:room_edit", args=[room.pk])
        self.client.post(edit_url, {"name": "Room B Renamed", "location": "", "is_active": "on"})
        room.refresh_from_db()
        self.assertEqual(room.name, "Room B Renamed")

    def test_room_toggle_active(self):
        self._login(self.committee_admin)
        self.assertTrue(self.room.is_active)
        self.client.post(reverse("adminpanel:room_toggle_active", args=[self.room.pk]))
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_active)

    def test_committee_admin_cannot_toggle_room_in_unmanaged_conference(self):
        other_room = Room.objects.create(conference=self.other_conference, name="Foreign Room")
        self._login(self.committee_admin)
        response = self.client.post(reverse("adminpanel:room_toggle_active", args=[other_room.pk]))
        self.assertEqual(response.status_code, 403)
        other_room.refresh_from_db()
        self.assertTrue(other_room.is_active)

    def test_committee_create_and_edit(self):
        self._login(self.committee_admin)
        create_url = reverse("adminpanel:committee_create", args=[self.conference.pk])
        response = self.client.post(
            create_url,
            {
                "name": "ECOSOC",
                "abbreviation": "ECOSOC",
                "committee_type": "ecosoc",
                "room": "",
                "description": "",
                "is_active": "on",
            },
        )
        committee = Committee.objects.get(name="ECOSOC", conference=self.conference)
        self.assertRedirects(
            response, reverse("adminpanel:conference_detail", args=[self.conference.pk])
        )

        edit_url = reverse("adminpanel:committee_edit", args=[committee.pk])
        self.client.post(
            edit_url,
            {
                "name": "ECOSOC Renamed",
                "abbreviation": "ECOSOC",
                "committee_type": "ecosoc",
                "room": "",
                "description": "",
                "is_active": "on",
            },
        )
        committee.refresh_from_db()
        self.assertEqual(committee.name, "ECOSOC Renamed")

    def test_committee_toggle_active(self):
        self._login(self.committee_admin)
        self.assertTrue(self.committee.is_active)
        self.client.post(reverse("adminpanel:committee_toggle_active", args=[self.committee.pk]))
        self.committee.refresh_from_db()
        self.assertFalse(self.committee.is_active)


class DelegateAndStaffAssignmentTests(AdminPanelTestBase):
    def test_assign_delegate_creates_new_account(self):
        self._login(self.committee_admin)
        self.assertFalse(User.objects.filter(email="newdel@example.com").exists())
        response = self.client.post(
            reverse("adminpanel:delegate_assign", args=[self.committee.pk]),
            {
                "email": "newdel@example.com",
                "name": "New Delegate",
                "country_name": "France",
                "country_code": "FRA",
            },
        )
        self.assertRedirects(
            response, reverse("adminpanel:committee_detail", args=[self.committee.pk])
        )
        user = User.objects.get(email="newdel@example.com")
        self.assertTrue(
            CountryAssignment.objects.filter(
                user=user, committee=self.committee, country_code="FRA"
            ).exists()
        )

    def test_assign_delegate_links_existing_account(self):
        existing = User.objects.create_user(
            email="existing@example.com", password=self.password, name="Existing Person"
        )
        self._login(self.committee_admin)
        self.client.post(
            reverse("adminpanel:delegate_assign", args=[self.committee.pk]),
            {
                "email": "existing@example.com",
                "country_name": "Kenya",
                "country_code": "KEN",
            },
        )
        self.assertTrue(
            CountryAssignment.objects.filter(
                user=existing, committee=self.committee, country_code="KEN"
            ).exists()
        )

    def test_assign_delegate_rejects_duplicate_active_country(self):
        self._login(self.committee_admin)
        response = self.client.post(
            reverse("adminpanel:delegate_assign", args=[self.committee.pk]),
            {
                "email": "seconddelegate@example.com",
                "name": "Second Delegate",
                "country_name": "India",
                "country_code": "IND",
            },
        )
        self.assertContains(response, "already actively represented")
        self.assertEqual(
            CountryAssignment.objects.filter(committee=self.committee, country_code="IND").count(),
            1,
        )

    def test_assign_delegate_requires_name_for_new_account(self):
        self._login(self.committee_admin)
        response = self.client.post(
            reverse("adminpanel:delegate_assign", args=[self.committee.pk]),
            {
                "email": "noname@example.com",
                "country_name": "Egypt",
                "country_code": "EGY",
            },
        )
        self.assertContains(response, "Enter a name")
        self.assertFalse(User.objects.filter(email="noname@example.com").exists())

    def test_committee_admin_cannot_assign_delegate_to_unmanaged_committee(self):
        other_committee = Committee.objects.create(
            conference=self.other_conference, name="ECOSOC", abbreviation="ECOSOC"
        )
        self._login(self.committee_admin)
        response = self.client.post(
            reverse("adminpanel:delegate_assign", args=[other_committee.pk]),
            {
                "email": "x@example.com",
                "name": "X",
                "country_name": "Nowhere",
                "country_code": "NOW",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_delegate_toggle_active(self):
        self._login(self.committee_admin)
        self.assertTrue(self.delegate_assignment.is_active)
        self.client.post(
            reverse("adminpanel:delegate_toggle_active", args=[self.delegate_assignment.pk])
        )
        self.delegate_assignment.refresh_from_db()
        self.assertFalse(self.delegate_assignment.is_active)

    def test_assign_staff_creates_new_account_with_role(self):
        self._login(self.committee_admin)
        response = self.client.post(
            reverse("adminpanel:staff_assign", args=[self.committee.pk]),
            {"email": "chair@example.com", "name": "New Chair", "role": "chair"},
        )
        self.assertRedirects(
            response, reverse("adminpanel:committee_detail", args=[self.committee.pk])
        )
        user = User.objects.get(email="chair@example.com")
        staff = CommitteeStaff.objects.get(user=user, committee=self.committee)
        self.assertEqual(staff.role, "chair")

    def test_assign_staff_rejects_duplicate_role_assignment(self):
        existing = User.objects.create_user(
            email="dupstaff@example.com", password=self.password, name="Dup Staff"
        )
        CommitteeStaff.objects.create(
            user=existing, committee=self.committee, role=CommitteeStaff.StaffRole.CHAIR
        )
        self._login(self.committee_admin)
        response = self.client.post(
            reverse("adminpanel:staff_assign", args=[self.committee.pk]),
            {"email": "dupstaff@example.com", "role": "vice_chair"},
        )
        self.assertRedirects(
            response, reverse("adminpanel:committee_detail", args=[self.committee.pk])
        )
        self.assertEqual(
            CommitteeStaff.objects.filter(user=existing, committee=self.committee).count(), 1
        )

    def test_staff_toggle_active(self):
        staff = CommitteeStaff.objects.create(
            user=self.delegate, committee=self.committee, role=CommitteeStaff.StaffRole.RAPPORTEUR
        )
        self._login(self.committee_admin)
        self.client.post(reverse("adminpanel:staff_toggle_active", args=[staff.pk]))
        staff.refresh_from_db()
        self.assertFalse(staff.is_active)


class AdminChitOversightTests(AdminPanelTestBase):
    def setUp(self):
        super().setUp()
        self.recipient = User.objects.create_user(
            email="recipient@example.com", password=self.password, name="Recipient"
        )
        self.recipient_assignment = CountryAssignment.objects.create(
            user=self.recipient, committee=self.committee, country_name="France", country_code="FRA"
        )
        self.chit = Chit.objects.create(
            conference=self.conference,
            committee=self.committee,
            room=self.room,
            sender=self.delegate,
            sender_country=self.delegate_assignment,
            recipient_country=self.recipient_assignment,
            recipient_type=RecipientType.DELEGATE,
            subject="Test admin oversight",
            message="Hello there.",
            status=Status.SUBMITTED,
        )

        other_committee = Committee.objects.create(
            conference=self.other_conference, name="ECOSOC", abbreviation="ECOSOC"
        )
        other_delegate = User.objects.create_user(
            email="otherdel@example.com", password=self.password, name="Other Delegate"
        )
        other_assignment = CountryAssignment.objects.create(
            user=other_delegate, committee=other_committee, country_name="Chile", country_code="CHL"
        )
        self.other_chit = Chit.objects.create(
            conference=self.other_conference,
            committee=other_committee,
            sender=other_delegate,
            sender_country=other_assignment,
            recipient_type=RecipientType.EXECUTIVE_BOARD,
            subject="Should not be visible",
            message="Other conference chit.",
            status=Status.SUBMITTED,
        )

    def test_chit_list_scoped_to_managed_conferences(self):
        self._login(self.committee_admin)
        response = self.client.get(reverse("adminpanel:chit_list"))
        chits = list(response.context["chits"])
        self.assertIn(self.chit, chits)
        self.assertNotIn(self.other_chit, chits)

    def test_super_admin_sees_all_chits(self):
        self._login(self.super_admin)
        response = self.client.get(reverse("adminpanel:chit_list"))
        chits = list(response.context["chits"])
        self.assertIn(self.chit, chits)
        self.assertIn(self.other_chit, chits)

    def test_chit_list_filter_by_status(self):
        Chit.objects.create(
            conference=self.conference,
            committee=self.committee,
            sender=self.delegate,
            sender_country=self.delegate_assignment,
            recipient_country=self.recipient_assignment,
            recipient_type=RecipientType.DELEGATE,
            message="Archived one.",
            status=Status.ARCHIVED,
        )
        self._login(self.committee_admin)
        response = self.client.get(reverse("adminpanel:chit_list"), {"status": "archived"})
        chits = list(response.context["chits"])
        self.assertEqual(len(chits), 1)
        self.assertEqual(chits[0].status, Status.ARCHIVED)

    def test_csv_export_scoped_and_contains_expected_row(self):
        self._login(self.committee_admin)
        response = self.client.get(reverse("adminpanel:chit_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

        content = response.content.decode("utf-8")
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        chit_numbers = [row[0] for row in rows[1:]]
        self.assertIn(self.chit.chit_number, chit_numbers)
        self.assertNotIn(self.other_chit.chit_number, chit_numbers)

    def test_delegate_cannot_access_admin_chit_export(self):
        self._login(self.delegate)
        response = self.client.get(reverse("adminpanel:chit_export"))
        self.assertRedirects(response, reverse("accounts:unauthorized"))


class AuditLogTests(AdminPanelTestBase):
    def test_actions_create_audit_log_entries(self):
        self._login(self.committee_admin)
        self.client.post(
            reverse("adminpanel:room_create", args=[self.conference.pk]),
            {"name": "Audited Room", "location": "", "is_active": "on"},
        )
        self.assertTrue(AuditLog.objects.filter(action="room_created").exists())

    def test_audit_log_never_contains_chit_message_text(self):
        # Sanity check on the AuditLog.record() contract itself: nothing in
        # this suite ever passes raw chit message content as metadata.
        self._login(self.committee_admin)
        self.client.post(
            reverse("adminpanel:committee_create", args=[self.conference.pk]),
            {
                "name": "New Committee",
                "abbreviation": "NC",
                "committee_type": "other",
                "room": "",
                "description": "",
                "is_active": "on",
            },
        )
        log = AuditLog.objects.filter(action="committee_created").first()
        self.assertIsNotNone(log)
        self.assertNotIn("message", log.metadata)

    def test_audit_log_filter_by_action(self):
        self._login(self.committee_admin)
        self.client.post(
            reverse("adminpanel:room_create", args=[self.conference.pk]),
            {"name": "Filter Room", "location": "", "is_active": "on"},
        )
        self._login(self.super_admin)
        response = self.client.get(reverse("adminpanel:audit_log"), {"action": "room_created"})
        logs = list(response.context["logs"])
        self.assertTrue(all(log.action == "room_created" for log in logs))
        self.assertTrue(len(logs) >= 1)
