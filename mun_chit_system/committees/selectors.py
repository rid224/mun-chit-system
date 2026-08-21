"""
Server-side resolution of "which committee/room does this user act in".

These helpers are the single source of truth used by chit submission views —
the committee and room attached to a chit are ALWAYS derived here from the
database, never accepted as raw client input for a delegate.
"""
from .models import CommitteeStaff, CountryAssignment


def get_active_country_assignments(user):
    """All active CountryAssignments for a delegate, across committees."""
    return (
        CountryAssignment.objects.filter(user=user, is_active=True, committee__is_active=True)
        .select_related("committee", "committee__room", "committee__conference")
    )


def get_active_country_assignment_for_committee(user, committee):
    """The single active CountryAssignment for this user in this committee, or None."""
    return get_active_country_assignments(user).filter(committee=committee).first()


def get_active_staff_assignments(user):
    """All active CommitteeStaff (EB) records for a user, across committees."""
    return (
        CommitteeStaff.objects.filter(user=user, is_active=True, committee__is_active=True)
        .select_related("committee", "committee__room", "committee__conference")
    )


def get_active_staff_assignment_for_committee(user, committee):
    return get_active_staff_assignments(user).filter(committee=committee).first()


def get_user_committees(user):
    """
    All committees a user is meaningfully attached to, whether as a
    delegate (CountryAssignment) or EB member (CommitteeStaff).
    Used to drive the "select a committee" screen when a user has more than one.
    """
    from committees.models import Committee

    delegate_committee_ids = get_active_country_assignments(user).values_list(
        "committee_id", flat=True
    )
    staff_committee_ids = get_active_staff_assignments(user).values_list(
        "committee_id", flat=True
    )
    ids = set(delegate_committee_ids) | set(staff_committee_ids)
    return Committee.objects.filter(id__in=ids).select_related("conference", "room")


def get_committee_context(user, committee):
    """
    Resolve how this user relates to a given committee: as a delegate (with
    their CountryAssignment) or as EB (with their CommitteeStaff record).
    Returns a dict {'role': 'delegate'|'executive_board', 'assignment': obj}
    or None if the user has no active standing in this committee.
    """
    staff = get_active_staff_assignment_for_committee(user, committee)
    if staff:
        return {"role": "executive_board", "assignment": staff}

    delegate = get_active_country_assignment_for_committee(user, committee)
    if delegate:
        return {"role": "delegate", "assignment": delegate}

    return None
