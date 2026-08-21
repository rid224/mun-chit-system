"""
Server-side role/committee permission mixins.

These are checked in EVERY protected view — never rely on hiding a link or
a JS check alone. A user's *effective* delegate/EB standing is derived from
their live CountryAssignment / CommitteeStaff records, not just the
denormalized User.role field, so a role field getting out of sync can never
grant access it shouldn't.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from committees.selectors import get_active_country_assignments, get_active_staff_assignments


class RoleRequiredMixin(LoginRequiredMixin):
    """
    Base mixin: requires login, then calls self.role_check(request.user).
    Subclasses implement role_check(). Failing the check redirects to the
    unauthorized page rather than raising a raw 403, so the user gets a
    readable explanation instead of Django's default error page.
    """

    def role_check(self, user) -> bool:
        raise NotImplementedError

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not self.role_check(request.user):
            return redirect("accounts:unauthorized")
        return super().dispatch(request, *args, **kwargs)


class DelegateRequiredMixin(RoleRequiredMixin):
    def role_check(self, user) -> bool:
        return user.is_super_admin or get_active_country_assignments(user).exists()


class ExecutiveBoardRequiredMixin(RoleRequiredMixin):
    def role_check(self, user) -> bool:
        return user.is_super_admin or get_active_staff_assignments(user).exists()


class CommitteeAdminRequiredMixin(RoleRequiredMixin):
    def role_check(self, user) -> bool:
        return user.is_super_admin or (
            user.is_committee_admin and user.managed_conferences.exists()
        )


class SuperAdminRequiredMixin(RoleRequiredMixin):
    def role_check(self, user) -> bool:
        return bool(user.is_super_admin)


def user_manages_conference(user, conference) -> bool:
    if user.is_super_admin:
        return True
    return user.is_committee_admin and user.managed_conferences.filter(pk=conference.pk).exists()


def require_conference_management(user, conference):
    if not user_manages_conference(user, conference):
        raise PermissionDenied("You do not manage this conference.")
