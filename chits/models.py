import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .querysets import ChitQuerySet


class RecipientType(models.TextChoices):
    DELEGATE = "delegate", "Delegate"
    EXECUTIVE_BOARD = "executive_board", "Executive Board"
    ADMINISTRATOR = "administrator", "Administrator"


class Category(models.TextChoices):
    POINT_OF_INFORMATION = "point_of_information", "Point of Information"
    PROCEDURAL_QUESTION = "procedural_question", "Procedural Question"
    MOTION_RELATED = "motion_related", "Motion Related"
    CLARIFICATION = "clarification", "Clarification"
    BILATERAL_COMMUNICATION = "bilateral_communication", "Bilateral Communication"
    OTHER = "other", "Other"


class Priority(models.TextChoices):
    NORMAL = "normal", "Normal"
    URGENT = "urgent", "Urgent"


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    DELIVERED = "delivered", "Delivered"
    READ = "read", "Read"
    REPLIED = "replied", "Replied"
    ARCHIVED = "archived", "Archived"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"


MAX_MESSAGE_LENGTH = 2000


class Chit(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    chit_number = models.CharField(
        max_length=40,
        unique=True,
        editable=False,
        blank=True,
        help_text="Human-readable chit number, e.g. MUN-2026-UNSC-000042",
    )

    conference = models.ForeignKey(
        "conferences.Conference", on_delete=models.CASCADE, related_name="chits"
    )
    committee = models.ForeignKey(
        "committees.Committee", on_delete=models.CASCADE, related_name="chits"
    )
    room = models.ForeignKey(
        "conferences.Room", on_delete=models.SET_NULL, null=True, related_name="chits"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_chits"
    )
    sender_country = models.ForeignKey(
        "committees.CountryAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_chits",
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_chits",
        help_text="Set for direct EB/Administrator targeting; may be null for shared EB inbox.",
    )
    recipient_country = models.ForeignKey(
        "committees.CountryAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_country_chits",
    )
    recipient_type = models.CharField(max_length=20, choices=RecipientType.choices)

    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField(max_length=MAX_MESSAGE_LENGTH)
    category = models.CharField(max_length=32, choices=Category.choices, default=Category.OTHER)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    is_anonymous = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = ChitQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["committee"]),
            models.Index(fields=["room"]),
            models.Index(fields=["sender"]),
            models.Index(fields=["recipient"]),
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.chit_number or str(self.public_id)

    def clean(self):
        # Prevent a delegate from sending a chit to their own country.
        if (
            self.sender_country_id
            and self.recipient_country_id
            and self.sender_country_id == self.recipient_country_id
        ):
            raise ValidationError("You cannot send a chit to your own country.")

        if len(self.message or "") > MAX_MESSAGE_LENGTH:
            raise ValidationError(
                f"Message exceeds the maximum length of {MAX_MESSAGE_LENGTH} characters."
            )

    def _generate_chit_number(self):
        abbrev = (self.committee.abbreviation or self.committee.name[:6]).upper().replace(" ", "")
        year = self.conference.year
        # A short, deterministic, per-conference disambiguator. chit_number
        # is globally unique across the whole system, but year+committee
        # abbreviation alone is NOT guaranteed unique — two different
        # conferences can easily reuse a common abbreviation like "UNSC" in
        # the same year. Without this, the second conference's first chit
        # would collide with the first conference's and fail to save.
        conference_short = str(self.conference.id).split("-")[0][:6].upper()
        with transaction.atomic():
            count = (
                Chit.objects.select_for_update()
                .filter(committee=self.committee)
                .exclude(chit_number="")
                .count()
            )
            return f"MUN-{year}-{abbrev}-{conference_short}-{count + 1:06d}"

    def save(self, *args, **kwargs):
        if not self.chit_number:
            self.chit_number = self._generate_chit_number()
        super().save(*args, **kwargs)


class ChitReply(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chit = models.ForeignKey(Chit, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chit_replies"
    )
    message = models.TextField(max_length=MAX_MESSAGE_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Reply to {self.chit.chit_number} by {self.author.name}"
