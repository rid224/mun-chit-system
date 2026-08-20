import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Append-only record of security/state-relevant actions.
    Never stores chit message content — only metadata (ids, status
    transitions, field names changed), so this table is safe to export
    or inspect without leaking private communications.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["action"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.object_type}:{self.object_id} by {self.actor}"

    @classmethod
    def record(cls, actor, action, obj, **metadata):
        """
        Convenience creator. `metadata` must never include raw chit message
        text — pass only structured, non-sensitive fields (status, ids, etc).
        """
        return cls.objects.create(
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=action,
            object_type=obj.__class__.__name__,
            object_id=str(getattr(obj, "pk", "")),
            metadata=metadata,
        )
