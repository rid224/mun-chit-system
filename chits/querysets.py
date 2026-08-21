from django.db import models
from django.db.models import Q


class ChitQuerySet(models.QuerySet):
    """
    Role-based visibility scoping. This is the authoritative authorization
    layer for chit access — views MUST filter through .visible_to(user)
    before returning any chit to a client, including single-object lookups
    (use get_object_or_404(Chit.objects.visible_to(user), ...)).
    """

    def visible_to(self, user):
        if user.is_super_admin:
            return self.all()

        if user.is_committee_admin:
            managed_conference_ids = user.managed_conferences.values_list("id", flat=True)
            return self.filter(conference_id__in=managed_conference_ids)

        if user.is_executive_board:
            from committees.selectors import get_active_staff_assignments

            eb_committee_ids = list(
                get_active_staff_assignments(user).values_list("committee_id", flat=True)
            )
            return self.filter(
                Q(committee_id__in=eb_committee_ids, recipient_type="executive_board")
                | Q(
                    committee_id__in=eb_committee_ids,
                    recipient_type="delegate",
                    is_via_eb=True,
                )
            )

        # Delegate (default): chits they sent, chits sent to their assigned
        # country, or chits directly addressed to them.
        from committees.selectors import get_active_country_assignments

        my_assignment_ids = get_active_country_assignments(user).values_list("id", flat=True)
        return self.filter(
            Q(sender=user)
            | Q(recipient_country_id__in=list(my_assignment_ids))
            | Q(recipient=user)
        )

    def for_committee(self, committee):
        return self.filter(committee=committee)

    def unread(self):
        return self.filter(read_at__isnull=True)

    def awaiting_response(self):
        return self.filter(status__in=["delivered", "read"])
