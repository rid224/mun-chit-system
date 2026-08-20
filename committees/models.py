import uuid

from django.conf import settings
from django.db import models


class Committee(models.Model):
    class CommitteeType(models.TextChoices):
        GENERAL_ASSEMBLY = "general_assembly", "General Assembly"
        SECURITY_COUNCIL = "security_council", "Security Council"
        ECOSOC = "ecosoc", "ECOSOC"
        CRISIS = "crisis", "Crisis Committee"
        SPECIALIZED_AGENCY = "specialized_agency", "Specialized Agency"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(
        "conferences.Conference", on_delete=models.CASCADE, related_name="committees"
    )
    name = models.CharField(max_length=200)
    abbreviation = models.CharField(max_length=20, blank=True)
    committee_type = models.CharField(
        max_length=32, choices=CommitteeType.choices, default=CommitteeType.OTHER
    )
    room = models.ForeignKey(
        "conferences.Room",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="committees",
        help_text="The committee's assigned room. Auto-attached to every chit sent from this committee.",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Per-committee override of the conference-level cross-committee toggle.
    allow_cross_committee_chits = models.BooleanField(
        default=False,
        help_text="If enabled (and conference allows it), delegates here may message other committees.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "name"], name="unique_committee_name_per_conference"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.conference.name})"


class CountryAssignment(models.Model):
    """
    Links a delegate (User) to the country they represent in a specific
    committee. A country may only be actively represented by one delegate
    per committee at a time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="country_assignments"
    )
    committee = models.ForeignKey(
        Committee, on_delete=models.CASCADE, related_name="country_assignments"
    )
    country_name = models.CharField(max_length=150)
    country_code = models.CharField(max_length=8, help_text="ISO-like short code, e.g. IND, USA")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["committee", "country_name"]
        constraints = [
            # Prevent two active delegates representing the same country in the same committee.
            models.UniqueConstraint(
                fields=["committee", "country_code"],
                condition=models.Q(is_active=True),
                name="unique_active_country_per_committee",
            )
        ]
        indexes = [
            models.Index(fields=["committee", "is_active"]),
        ]

    def __str__(self):
        return f"{self.country_name} — {self.committee.name} ({self.user.name})"


class CommitteeStaff(models.Model):
    class StaffRole(models.TextChoices):
        CHAIR = "chair", "Chair"
        VICE_CHAIR = "vice_chair", "Vice Chair"
        DIRECTOR = "director", "Director"
        RAPPORTEUR = "rapporteur", "Rapporteur"
        MODERATOR = "moderator", "Moderator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_assignments"
    )
    committee = models.ForeignKey(Committee, on_delete=models.CASCADE, related_name="staff")
    role = models.CharField(max_length=20, choices=StaffRole.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["committee", "role"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "committee"], name="unique_staff_per_user_per_committee"
            )
        ]
        indexes = [
            models.Index(fields=["committee", "is_active"]),
        ]

    def __str__(self):
        return f"{self.get_role_display()} — {self.committee.name} ({self.user.name})"
