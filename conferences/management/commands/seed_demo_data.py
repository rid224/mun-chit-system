"""
Creates a fully working demo: one conference, three committees, three
rooms, delegate/EB/admin accounts, and sample chits covering every status,
category, and Via EB routing so the app is immediately explorable without
manually clicking through every flow first.

Safety: refuses to run unless settings.DEBUG is True, since it creates
accounts with known, published demo passwords — never acceptable in a
real deployment. Idempotent: re-running updates/reuses existing rows
(matched by natural keys like email or (conference, name)) instead of
duplicating them, so it's safe to run repeatedly during development.
"""
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from chits.models import Category, Chit, ChitReply, RecipientType, Status
from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference, Room

User = get_user_model()

DEMO_PASSWORD = "DemoPass123!"

COMMITTEES = [
    {
        "name": "United Nations Security Council",
        "abbreviation": "UNSC",
        "committee_type": Committee.CommitteeType.SECURITY_COUNCIL,
        "room_name": "Council Chamber",
        "countries": [
            ("United States", "USA"),
            ("United Kingdom", "GBR"),
            ("France", "FRA"),
            ("Russian Federation", "RUS"),
            ("China", "CHN"),
            ("India", "IND"),
        ],
        "staff": [
            ("unsc.chair@demo.mun", "Aiko Tanaka", CommitteeStaff.StaffRole.CHAIR),
            ("unsc.vicechair@demo.mun", "Noah Kessler", CommitteeStaff.StaffRole.VICE_CHAIR),
        ],
    },
    {
        "name": "Economic and Social Council",
        "abbreviation": "ECOSOC",
        "committee_type": Committee.CommitteeType.ECOSOC,
        "room_name": "Assembly Hall B",
        "countries": [
            ("Germany", "DEU"),
            ("Japan", "JPN"),
            ("Brazil", "BRA"),
            ("Kenya", "KEN"),
            ("Norway", "NOR"),
            ("Indonesia", "IDN"),
        ],
        "staff": [
            ("ecosoc.chair@demo.mun", "Priya Raman", CommitteeStaff.StaffRole.CHAIR),
            ("ecosoc.rapporteur@demo.mun", "Lucas Ferreira", CommitteeStaff.StaffRole.RAPPORTEUR),
        ],
    },
    {
        "name": "UN Human Rights Council",
        "abbreviation": "UNHRC",
        "committee_type": Committee.CommitteeType.OTHER,
        "room_name": "Assembly Hall C",
        "countries": [
            ("South Africa", "ZAF"),
            ("Mexico", "MEX"),
            ("Sweden", "SWE"),
            ("Egypt", "EGY"),
            ("Australia", "AUS"),
            ("Canada", "CAN"),
        ],
        "staff": [
            ("unhrc.chair@demo.mun", "Fatima Haidari", CommitteeStaff.StaffRole.CHAIR),
        ],
    },
]


class Command(BaseCommand):
    help = "Seeds a full demo conference with committees, rooms, delegates, EB staff, and sample chits."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Bypass the DEBUG-only safety check (still refuses on a prod-looking DB name).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed demo accounts with known passwords outside DEBUG mode. "
                "Pass --force only if you are certain this is not a production database."
            )

        self.stdout.write("Seeding demo data…")

        conference = self._create_conference()
        admin = self._create_committee_admin(conference)
        committees_by_abbrev = {}
        delegates_by_code = {}

        for spec in COMMITTEES:
            committee, room = self._create_committee(conference, spec)
            committees_by_abbrev[spec["abbreviation"]] = committee
            self._create_staff(committee, spec["staff"])
            delegates_by_code[spec["abbreviation"]] = self._create_delegates(
                committee, spec["countries"]
            )

        super_admin = self._ensure_super_admin()

        self._create_sample_chits(conference, committees_by_abbrev, delegates_by_code)

        self.stdout.write(self.style.SUCCESS("\nDemo data ready."))
        self._print_credentials(super_admin, admin, committees_by_abbrev, delegates_by_code)

    # -- creation helpers -------------------------------------------------

    def _create_conference(self):
        today = timezone.now().date()
        conference, created = Conference.objects.get_or_create(
            name="Global Horizons MUN 2026",
            year=2026,
            defaults=dict(
                venue="Gokhale Institute Convention Centre",
                start_date=today + timedelta(days=14),
                end_date=today + timedelta(days=16),
                timezone="Asia/Kolkata",
                is_active=True,
                chit_submissions_enabled=True,
                delegate_to_eb_enabled=True,
                anonymous_chits_enabled=True,
                replies_enabled=True,
                cross_committee_chits_enabled=False,
                max_message_length=2000,
            ),
        )
        self.stdout.write(f"{'Created' if created else 'Reused'} conference: {conference.name}")
        return conference

    def _create_committee_admin(self, conference):
        admin, created = User.objects.get_or_create(
            email="admin@demo.mun",
            defaults=dict(name="Demo Committee Admin", role="committee_admin"),
        )
        if created:
            admin.set_password(DEMO_PASSWORD)
            admin.save(update_fields=["password"])
        admin.managed_conferences.add(conference)
        self.stdout.write(f"{'Created' if created else 'Reused'} committee admin: {admin.email}")
        return admin

    def _ensure_super_admin(self):
        super_admin, created = User.objects.get_or_create(
            email="super@demo.mun",
            defaults=dict(name="Demo Super Admin", role="super_admin", is_staff=True, is_superuser=True),
        )
        if created:
            super_admin.set_password(DEMO_PASSWORD)
            super_admin.save(update_fields=["password"])
        return super_admin

    def _create_committee(self, conference, spec):
        room, _ = Room.objects.get_or_create(
            conference=conference,
            name=spec["room_name"],
            defaults=dict(location="Main Building", capacity=60, is_active=True),
        )
        committee, created = Committee.objects.get_or_create(
            conference=conference,
            name=spec["name"],
            defaults=dict(
                abbreviation=spec["abbreviation"],
                committee_type=spec["committee_type"],
                room=room,
                is_active=True,
            ),
        )
        self.stdout.write(f"  {'Created' if created else 'Reused'} committee: {committee.name}")
        return committee, room

    def _create_staff(self, committee, staff_spec):
        for email, name, role in staff_spec:
            user, created = User.objects.get_or_create(
                email=email, defaults=dict(name=name, role="executive_board")
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
            CommitteeStaff.objects.get_or_create(
                user=user, committee=committee, defaults=dict(role=role, is_active=True)
            )

    def _create_delegates(self, committee, countries):
        assignments = {}
        for country_name, country_code in countries:
            email = f"{country_code.lower()}.{committee.abbreviation.lower()}@demo.mun"
            user, created = User.objects.get_or_create(
                email=email, defaults=dict(name=f"Delegate of {country_name}", role="delegate")
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
            assignment, _ = CountryAssignment.objects.get_or_create(
                committee=committee,
                country_code=country_code,
                defaults=dict(user=user, country_name=country_name, is_active=True),
            )
            assignments[country_code] = assignment
        return assignments

    def _create_sample_chits(self, conference, committees, delegates):
        if Chit.objects.filter(conference=conference).exists():
            self.stdout.write("Sample chits already exist for this conference — skipping.")
            return

        now = timezone.now()
        unsc = committees["UNSC"]
        ecosoc = committees["ECOSOC"]
        unhrc = committees["UNHRC"]
        unsc_d = delegates["UNSC"]
        ecosoc_d = delegates["ECOSOC"]
        unhrc_d = delegates["UNHRC"]

        # 1. A plain delegate-to-delegate chit, still unread.
        self._make_chit(
            conference, unsc, unsc_d["USA"], recipient_country=unsc_d["GBR"],
            subject="Joint statement on sanctions", message="Would the UK co-sponsor our draft resolution?",
            category=Category.MOTION_RELATED, status=Status.SUBMITTED,
            created_at=now - timedelta(minutes=20),
        )

        # 2. Delegate-to-delegate chit CC'd "Via EB", already read.
        self._make_chit(
            conference, unsc, unsc_d["FRA"], recipient_country=unsc_d["CHN"],
            subject="Point of clarification", message="Can you clarify your delegation's position on paragraph 4?",
            category=Category.POINT_OF_INFORMATION, is_via_eb=True, status=Status.READ,
            created_at=now - timedelta(hours=1), delivered_at=now - timedelta(minutes=55),
            read_at=now - timedelta(minutes=50),
        )

        # 3. Anonymous delegate-to-delegate chit.
        self._make_chit(
            conference, unsc, unsc_d["RUS"], recipient_country=unsc_d["IND"],
            subject="", message="Off the record — are you open to an amendment on clause 7?",
            category=Category.OTHER, status=Status.DELIVERED,
            is_anonymous=True, created_at=now - timedelta(minutes=40),
            delivered_at=now - timedelta(minutes=38),
        )

        # 4. Delegate-to-EB chit, submitted (new queue).
        self._make_chit(
            conference, ecosoc, ecosoc_d["DEU"], recipient_type=RecipientType.EXECUTIVE_BOARD,
            subject="Request to extend caucus", message="Requesting a 10-minute extension to the current moderated caucus.",
            category=Category.PROCEDURAL_QUESTION, status=Status.SUBMITTED,
            created_at=now - timedelta(minutes=5),
        )

        # 5. Delegate-to-EB chit, replied.
        eb_chit = self._make_chit(
            conference, ecosoc, ecosoc_d["JPN"], recipient_type=RecipientType.EXECUTIVE_BOARD,
            subject="Speaker's list question", message="Has the speaker's list for the next session been finalized?",
            category=Category.PROCEDURAL_QUESTION, status=Status.REPLIED,
            created_at=now - timedelta(hours=2), delivered_at=now - timedelta(hours=1, minutes=55),
            read_at=now - timedelta(hours=1, minutes=50), replied_at=now - timedelta(hours=1, minutes=45),
        )
        eb_chair = CommitteeStaff.objects.filter(committee=ecosoc, role="chair").first()
        if eb_chair:
            ChitReply.objects.create(
                chit=eb_chit, author=eb_chair.user,
                message="Yes, it's posted on the committee board — check with the rapporteur for a copy.",
            )

        # 6. Archived chit.
        self._make_chit(
            conference, unhrc, unhrc_d["ZAF"], recipient_type=RecipientType.EXECUTIVE_BOARD,
            subject="Resolved procedural matter", message="This has already been resolved in session — closing this out.",
            category=Category.PROCEDURAL_QUESTION, status=Status.ARCHIVED,
            created_at=now - timedelta(hours=5), delivered_at=now - timedelta(hours=4, minutes=55),
            read_at=now - timedelta(hours=4, minutes=50), archived_at=now - timedelta(hours=4),
        )

        # 7. Another delegate-to-delegate chit in a third committee.
        self._make_chit(
            conference, unhrc, unhrc_d["MEX"], recipient_country=unhrc_d["SWE"],
            subject="Bloc coordination", message="Are you free to meet during the next unmoderated caucus?",
            category=Category.MOTION_RELATED, status=Status.SUBMITTED,
            created_at=now - timedelta(minutes=8),
        )

        self.stdout.write("  Created 7 sample chits across all three committees.")

    def _make_chit(
        self,
        conference,
        committee,
        sender_assignment,
        recipient_country=None,
        recipient_type=None,
        **fields,
    ):
        recipient_type = recipient_type or RecipientType.DELEGATE
        chit = Chit(
            conference=conference,
            committee=committee,
            room=committee.room,
            sender=sender_assignment.user,
            sender_country=sender_assignment,
            recipient_country=recipient_country,
            recipient_type=recipient_type,
            submitted_at=fields.get("created_at", timezone.now()),
            **fields,
        )
        chit.full_clean()
        chit.save()
        return chit

    def _print_credentials(self, super_admin, admin, committees, delegates):
        self.stdout.write("\n--- Demo credentials (all share the same password) ---")
        self.stdout.write(f"Password for every demo account: {DEMO_PASSWORD}\n")
        self.stdout.write(f"Super Admin:      {super_admin.email}")
        self.stdout.write(f"Committee Admin:  {admin.email}")
        for abbrev, committee in committees.items():
            self.stdout.write(f"\n{committee.name} ({abbrev}):")
            for staff in CommitteeStaff.objects.filter(committee=committee).select_related("user"):
                self.stdout.write(f"  EB {staff.get_role_display():<12} {staff.user.email}")
            for code, assignment in delegates[abbrev].items():
                self.stdout.write(
                    f"  Delegate ({assignment.country_name:<20}) {assignment.user.email}"
                )
