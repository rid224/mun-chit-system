from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView, UpdateView

from committees.selectors import get_user_committees
from .forms import EmailAuthenticationForm, ProfileForm
from .rate_limit import (
    clear_attempts,
    is_rate_limited,
    rate_limit_identifier,
    register_failed_attempt,
)


class LandingView(TemplateView):
    template_name = "public/landing.html"


class UnauthorizedView(TemplateView):
    template_name = "public/unauthorized.html"


class RateLimitedLoginView(auth_views.LoginView):
    """
    Wraps Django's built-in LoginView with a simple cache-based rate limit,
    keyed on IP + attempted email, so repeated password guesses against one
    account (or from one source) get throttled without needing external
    infrastructure. Successful login clears the counter for that identifier.
    """

    authentication_form = EmailAuthenticationForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        email = request.POST.get("username", "")
        identifier = rate_limit_identifier(request, email)
        if is_rate_limited(identifier):
            messages.error(
                request,
                "Too many failed login attempts. Please wait a few minutes before trying again.",
            )
            return render(request, self.template_name, {"form": self.get_form()})
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data.get("username", "")
        clear_attempts(rate_limit_identifier(self.request, email))
        return super().form_valid(form)

    def form_invalid(self, form):
        email = self.request.POST.get("username", "")
        register_failed_attempt(rate_limit_identifier(self.request, email))
        return super().form_invalid(form)


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("accounts:login")


class DashboardRedirectView(LoginRequiredMixin, View):
    """
    Sends a freshly-logged-in user to the right place for their role.
    For delegates/EB members with more than one committee, routes through
    the committee selector first; the selector stores the choice in the
    session and redirects onward from there.
    """

    def get(self, request, *args, **kwargs):
        user = request.user

        if user.is_super_admin or user.is_committee_admin:
            return redirect("adminpanel:dashboard")

        committees = list(get_user_committees(user))

        if not committees:
            messages.info(
                request,
                "You don't have an active committee assignment yet. "
                "Contact your conference administrator.",
            )
            return redirect("accounts:unauthorized")

        if len(committees) > 1:
            return redirect("committees:select")

        request.session["active_committee_id"] = str(committees[0].id)

        if user.is_executive_board:
            return redirect("chits:eb_dashboard")
        return redirect("chits:delegate_dashboard")


class ProfileView(LoginRequiredMixin, UpdateView):
    template_name = "accounts/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Profile updated.")
        return super().form_valid(form)
