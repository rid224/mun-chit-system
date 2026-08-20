import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """
    Simple in-app notification, delivered via periodic polling in v1.
    See notifications/consumers.py for the drop-in Django Channels upgrade
    path documented in the README.
    """

    class Kind(models.TextChoices):
        NEW_CHIT = "new_chit", "New chit received"
        CHIT_READ = "chit_read", "Your chit was read"
        CHIT_REPLIED = "chit_replied", "Your chit was replied to"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    chit = models.ForeignKey(
        "chits.Chit", on_delete=models.CASCADE, related_name="notifications", null=True
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} → {self.user.name}"
