"""
Object-level scoping helpers for the admin panel. A Committee Administrator
may only see/manage conferences in their `managed_conferences`; a Super
Administrator sees everything. Every admin panel view goes through one of
these rather than querying models directly, so the scoping rule lives in
exactly one place.
"""
from conferences.models import Conference


def managed_conferences_for(user):
    if user.is_super_admin:
        return Conference.objects.all()
    return user.managed_conferences.all()


def managed_committees_for(user):
    from committees.models import Committee

    return Committee.objects.filter(conference__in=managed_conferences_for(user))
