from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .models import Committee
from .selectors import get_committee_context, get_user_committees


class CommitteeSelectView(LoginRequiredMixin, View):
    """
    Shown when a user has an active standing (delegate or EB) in more than
    one committee. The user's choice is stored server-side in the session
    and is the ONLY thing later views trust for "which committee is this
    request acting in" — it is re-validated against live assignment
    records every time it's read (see get_committee_context), so a stale
    or tampered session value can't grant access to a committee the user
    no longer belongs to.
    """

    template_name = "committees/select.html"

    def get(self, request, *args, **kwargs):
        committees = get_user_committees(request.user)
        if committees.count() <= 1:
            return redirect("accounts:dashboard_redirect")
        return render(request, self.template_name, {"committees": committees})

    def post(self, request, *args, **kwargs):
        committee_id = request.POST.get("committee_id")
        committee = get_object_or_404(
            get_user_committees(request.user), id=committee_id
        )
        context = get_committee_context(request.user, committee)
        if context is None:
            messages.error(request, "You no longer have an active assignment in that committee.")
            return redirect("committees:select")

        request.session["active_committee_id"] = str(committee.id)

        if context["role"] == "executive_board":
            return redirect("chits:eb_dashboard")
        return redirect("chits:delegate_dashboard")
