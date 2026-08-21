from django.db.models.signals import post_save
from django.dispatch import receiver

from .middleware import get_current_user
from .models import AuditLog


def connect():
    from chits.models import Chit, ChitReply

    post_save.connect(_log_chit_save, sender=Chit, dispatch_uid="audit_chit_save")
    post_save.connect(_log_reply_save, sender=ChitReply, dispatch_uid="audit_reply_save")


def _log_chit_save(sender, instance, created, **kwargs):
    actor = get_current_user()
    AuditLog.record(
        actor,
        action="chit_created" if created else "chit_updated",
        obj=instance,
        status=instance.status,
        committee_id=str(instance.committee_id),
        conference_id=str(instance.conference_id),
    )


def _log_reply_save(sender, instance, created, **kwargs):
    if not created:
        return
    actor = get_current_user()
    AuditLog.record(
        actor,
        action="chit_replied",
        obj=instance,
        chit_id=str(instance.chit_id),
    )


@receiver(post_save, sender=None)
def _noop(sender, **kwargs):  # placeholder to keep receiver import used cleanly
    pass
