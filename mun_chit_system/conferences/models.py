import uuid

from django.db import models


class Conference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    year = models.PositiveIntegerField()
    venue = models.CharField(max_length=255, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        help_text="IANA timezone name, e.g. Asia/Kolkata",
    )
    is_active = models.BooleanField(default=True)

    # Feature toggles controlled by administrators (see admin settings requirements)
    chit_submissions_enabled = models.BooleanField(default=True)
    delegate_to_eb_enabled = models.BooleanField(default=True)
    anonymous_chits_enabled = models.BooleanField(default=False)
    replies_enabled = models.BooleanField(default=True)
    cross_committee_chits_enabled = models.BooleanField(default=False)
    max_message_length = models.PositiveIntegerField(default=2000)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="conference_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.year})"


class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=255, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    meeting_link = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("conference", "name")]

    def __str__(self):
        return f"{self.name} ({self.conference.name})"
