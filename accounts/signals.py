from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from audit.models import AuditLog


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditLog.record(user, action="login_success", obj=user)


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is not None:
        AuditLog.record(user, action="logout", obj=user)


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs):
    # Never log the attempted password. Only the attempted identifier (email).
    email = credentials.get("username", "unknown")
    AuditLog.objects.create(
        actor=None,
        action="login_failed",
        object_type="User",
        object_id="",
        metadata={"attempted_email": email},
    )
