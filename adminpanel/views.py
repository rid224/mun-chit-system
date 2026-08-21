import csv

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from accounts.models import Role
from accounts.permissions import (
    CommitteeAdminRequiredMixin,
    SuperAdminRequiredMixin,
    require_conference_management,
)
from audit.models import AuditLog
from chits.models import Category, Chit, Status
from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference, Room

from .forms import (
    CommitteeForm,
    CommitteeStaffAssignForm,
    ConferenceForm,
    ConferenceSettingsForm,
    DelegateAssignForm,
    RoomForm,
)
from .selectors import managed_committees_for, managed_conferences_for

User = get_user_model()


def _require_conference_access(user, conference):
    require_conference_management(user, conference)


def _require_committee_access(user, committee):
    require_conference_management(user, committee.conference)


def _get_or_create_delegate_account(email, name, role):
    """
    Returns (user, was_created, temporary_password_or_None). Looking a
    person up by email is case-insensitive since that's how login works.
    """
    try:
        return User.objects.get(email__iexact=email), False, None
    except User.DoesNotExist:
        temp_password = get_random_string(12)
        user = User.objects.create_user(
            email=email, password=temp_password, name=name, role=role
        )
        return user, True, temp_password


class AdminDashboardView(CommitteeAdminRequiredMixin, TemplateView):
    template_name = "adminpanel/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        conferences = managed_conferences_for(user)
        chits = Chit.objects.filter(conference__in=conferences)

        context["managed_conferences"] = conferences if not user.is_superuser else None
        context["conference_count"] = conferences.count()
        context["committee_count"] = managed_committees_for(user).count()
        context["delegate_count"] = CountryAssignment.objects.filter(
            committee__conference__in=conferences, is_active=True
        ).count()
        context["total_chits"] = chits.count()
        context["status_breakdown"] = list(
            chits.values("status").annotate(count=Count("id")).order_by("-count")
        )
        context["category_breakdown"] = list(
            chits.values("category").annotate(count=Count("id")).order_by("-count")
        )
        return context


class ConferenceListView(CommitteeAdminRequiredMixin, ListView):
    template_name = "adminpanel/conference_list.html"
    context_object_name = "conferences"

    def get_queryset(self):
        return managed_conferences_for(self.request.user).order_by("-year", "name")


class ConferenceCreateView(SuperAdminRequiredMixin, View):
    """
    Only Super Admins create new conferences. Committee Administrators
    manage conferences that have already been assigned to them via
    `managed_conferences` — that assignment itself is done through Django
    Admin (or a future Phase 6 feature), not this panel, since it's a
    rare, high-trust action better suited to the audited built-in admin.
    """

    template_name = "adminpanel/conference_form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ConferenceForm(), "verb": "Create"})

    def post(self, request):
        form = ConferenceForm(request.POST)
        if form.is_valid():
            conference = form.save()
            AuditLog.record(request.user, "conference_created", conference, name=conference.name)
            messages.success(request, f"{conference.name} created.")
            return redirect("adminpanel:conference_detail", pk=conference.pk)
        return render(request, self.template_name, {"form": form, "verb": "Create"})


class ConferenceDetailView(CommitteeAdminRequiredMixin, DetailView):
    model = Conference
    template_name = "adminpanel/conference_detail.html"
    context_object_name = "conference"

    def get_object(self, queryset=None):
        obj = get_object_or_404(Conference, pk=self.kwargs["pk"])
        _require_conference_access(self.request.user, obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        conference = self.object
        context["rooms"] = conference.rooms.all()
        context["committees"] = conference.committees.select_related("room").all()
        return context


class ConferenceEditView(CommitteeAdminRequiredMixin, View):
    template_name = "adminpanel/conference_form.html"

    def _get_conference(self):
        conference = get_object_or_404(Conference, pk=self.kwargs["pk"])
        _require_conference_access(self.request.user, conference)
        return conference

    def get(self, request, pk):
        conference = self._get_conference()
        form = ConferenceForm(instance=conference)
        return render(request, self.template_name, {"form": form, "verb": "Edit", "conference": conference})

    def post(self, request, pk):
        conference = self._get_conference()
        form = ConferenceForm(request.POST, instance=conference)
        if form.is_valid():
            form.save()
            AuditLog.record(request.user, "conference_edited", conference)
            messages.success(request, f"{conference.name} updated.")
            return redirect("adminpanel:conference_detail", pk=conference.pk)
        return render(request, self.template_name, {"form": form, "verb": "Edit", "conference": conference})


class ConferenceSettingsView(CommitteeAdminRequiredMixin, View):
    template_name = "adminpanel/conference_settings.html"

    def _get_conference(self):
        conference = get_object_or_404(Conference, pk=self.kwargs["pk"])
        _require_conference_access(self.request.user, conference)
        return conference

    def get(self, request, pk):
        conference = self._get_conference()
        form = ConferenceSettingsForm(instance=conference)
        return render(request, self.template_name, {"form": form, "conference": conference})

    def post(self, request, pk):
        conference = self._get_conference()
        form = ConferenceSettingsForm(request.POST, instance=conference)
        if form.is_valid():
            form.save()
            AuditLog.record(request.user, "conference_settings_changed", conference)
            messages.success(request, "Settings updated.")
            return redirect("adminpanel:conference_detail", pk=conference.pk)
        return render(request, self.template_name, {"form": form, "conference": conference})


class RoomCreateView(CommitteeAdminRequiredMixin, View):
    template_name = "adminpanel/room_form.html"

    def _get_conference(self):
        conference = get_object_or_404(Conference, pk=self.kwargs["conference_pk"])
        _require_conference_access(self.request.user, conference)
        return conference

    def get(self, request, conference_pk):
        conference = self._get_conference()
        return render(
            request,
            self.template_name,
            {"form": RoomForm(), "verb": "Create", "conference": conference},
        )

    def post(self, request, conference_pk):
        conference = self._get_conference()
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.conference = conference
            room.save()
            AuditLog.record(request.user, "room_created", room, conference=conference.name)
            messages.success(request, f"Room {room.name} created.")
            return redirect("adminpanel:conference_detail", pk=conference.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "verb": "Create", "conference": conference},
        )


class RoomEditView(CommitteeAdminRequiredMixin, View):
    template_name = "adminpanel/room_form.html"

    def _get_room(self):
        room = get_object_or_404(Room, pk=self.kwargs["pk"])
        _require_conference_access(self.request.user, room.conference)
        return room

    def get(self, request, pk):
        room = self._get_room()
        return render(
            request,
            self.template_name,
            {"form": RoomForm(instance=room), "verb": "Edit", "conference": room.conference},
        )

    def post(self, request, pk):
        room = self._get_room()
        form = RoomForm(request.POST, instance=room)
        if form.is_valid():
            form.save()
            AuditLog.record(request.user, "room_edited", room)
            messages.success(request, f"Room {room.name} updated.")
            return redirect("adminpanel:conference_detail", pk=room.conference.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "verb": "Edit", "conference": room.conference},
        )


class RoomToggleActiveView(CommitteeAdminRequiredMixin, View):
    def post(self, request, pk):
        room = get_object_or_404(Room, pk=pk)
        _require_conference_access(request.user, room.conference)
        room.is_active = not room.is_active
        room.save(update_fields=["is_active"])
        AuditLog.record(request.user, "room_toggled_active", room, is_active=room.is_active)
        messages.success(request, f"Room {room.name} is now {'active' if room.is_active else 'inactive'}.")
        return redirect("adminpanel:conference_detail", pk=room.conference.pk)


class CommitteeCreateView(CommitteeAdminRequiredMixin, View):
    template_name = "adminpanel/committee_form.html"

    def _get_conference(self):
        conference = get_object_or_404(Conference, pk=self.kwargs["conference_pk"])
        _require_conference_access(self.request.user, conference)
        return conference

    def get(self, request, conference_pk):
        conference = self._get_conference()
        form = CommitteeForm(conference=conference)
        return render(
            request, self.template_name, {"form": form, "verb": "Create", "conference": conference}
        )

    def post(self, request, conference_pk):
        conference = self._get_conference()
        form = CommitteeForm(request.POST, conference=conference)
        if form.is_valid():
            committee = form.save(commit=False)
            committee.conference = conference
            committee.save()
            AuditLog.record(request.user, "committee_created", committee, conference=conference.name)
            messages.success(request, f"{committee.name} created.")
            return redirect("adminpanel:conference_detail", pk=conference.pk)
        return render(
            request, self.template_name, {"form": form, "verb": "Create", "conference": conference}
        )


class CommitteeEditView(CommitteeAdminRequiredMixin, View):
    template_name = "adminpanel/committee_form.html"

    def _get_committee(self):
        committee = get_object_or_404(Committee, pk=self.kwargs["pk"])
        _require_committee_access(self.request.user, committee)
        return committee

    def get(self, request, pk):
        committee = self._get_committee()
        form = CommitteeForm(instance=committee, conference=committee.conference)
        return render(
            request,
            self.template_name,
            {"form": form, "verb": "Edit", "conference": committee.conference, "committee": committee},
        )

    def post(self, request, pk):
        committee = self._get_committee()
        form = CommitteeForm(request.POST, instance=committee, conference=committee.conference)
        if form.is_valid():
            form.save()
            AuditLog.record(request.user, "committee_edited", committee)
            messages.success(request, f"{committee.name} updated.")
            return redirect("adminpanel:committee_detail", pk=committee.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "verb": "Edit", "conference": committee.conference, "committee": committee},
        )


class CommitteeToggleActiveView(CommitteeAdminRequiredMixin, View):
    def post(self, request, pk):
        committee = get_object_or_404(Committee, pk=pk)
        _require_committee_access(request.user, committee)
        committee.is_active = not committee.is_active
        committee.save(update_fields=["is_active"])
        AuditLog.record(request.user, "committee_toggled_active", committee, is_active=committee.is_active)
        messages.success(
            request, f"{committee.name} is now {'active' if committee.is_active else 'inactive'}."
        )
        return redirect("adminpanel:conference_detail", pk=committee.conference.pk)


class CommitteeDetailView(CommitteeAdminRequiredMixin, View):
    """
    Delegate roster + EB staff roster for a committee, with inline
    assign forms for both. GET renders the page; the two POST actions
    (assign delegate, assign staff) are handled by separate views below
    so their URLs/forms stay independent, but on validation failure they
    re-render this same template directly (not a redirect) so field
    errors are visible without losing form state.
    """

    template_name = "adminpanel/committee_detail.html"

    def _get_committee(self):
        committee = get_object_or_404(Committee, pk=self.kwargs["pk"])
        _require_committee_access(self.request.user, committee)
        return committee

    def get(self, request, pk):
        committee = self._get_committee()
        return render(request, self.template_name, self._context(committee))

    def _context(self, committee, delegate_form=None, staff_form=None):
        return {
            "committee": committee,
            "conference": committee.conference,
            "delegates": committee.country_assignments.select_related("user").all(),
            "staff": committee.staff.select_related("user").all(),
            "delegate_form": delegate_form or DelegateAssignForm(committee=committee),
            "staff_form": staff_form or CommitteeStaffAssignForm(committee=committee),
        }


class DelegateAssignView(CommitteeAdminRequiredMixin, View):
    def post(self, request, committee_pk):
        committee = get_object_or_404(Committee, pk=committee_pk)
        _require_committee_access(request.user, committee)

        form = DelegateAssignForm(request.POST, committee=committee)
        if not form.is_valid():
            detail_view = CommitteeDetailView()
            return render(
                request,
                detail_view.template_name,
                detail_view._context(committee, delegate_form=form),
            )

        user, created, temp_password = _get_or_create_delegate_account(
            form.cleaned_data["email"], form.cleaned_data.get("name") or "", Role.DELEGATE
        )
        assignment = CountryAssignment.objects.create(
            user=user,
            committee=committee,
            country_name=form.cleaned_data["country_name"],
            country_code=form.cleaned_data["country_code"],
        )
        AuditLog.record(
            request.user,
            "delegate_assigned",
            assignment,
            committee=committee.name,
            country=assignment.country_code,
        )
        if created:
            messages.success(
                request,
                f"Created a new account for {user.email} and assigned them "
                f"{assignment.country_name}. Temporary password: {temp_password} "
                "— share this with the delegate directly; there's no self-service "
                "reset yet.",
            )
        else:
            messages.success(request, f"{assignment.country_name} assigned to {user.name}.")
        return redirect("adminpanel:committee_detail", pk=committee.pk)


class CommitteeStaffAssignView(CommitteeAdminRequiredMixin, View):
    def post(self, request, committee_pk):
        committee = get_object_or_404(Committee, pk=committee_pk)
        _require_committee_access(request.user, committee)

        form = CommitteeStaffAssignForm(request.POST, committee=committee)
        if not form.is_valid():
            detail_view = CommitteeDetailView()
            return render(
                request,
                detail_view.template_name,
                detail_view._context(committee, staff_form=form),
            )

        user, created, temp_password = _get_or_create_delegate_account(
            form.cleaned_data["email"], form.cleaned_data.get("name") or "", Role.EXECUTIVE_BOARD
        )
        if CommitteeStaff.objects.filter(user=user, committee=committee).exists():
            messages.error(request, f"{user.name} already has a staff role in this committee.")
            return redirect("adminpanel:committee_detail", pk=committee.pk)

        staff = CommitteeStaff.objects.create(
            user=user, committee=committee, role=form.cleaned_data["role"]
        )
        AuditLog.record(
            request.user, "staff_assigned", staff, committee=committee.name, role=staff.role
        )
        if created:
            messages.success(
                request,
                f"Created a new account for {user.email} and assigned them as "
                f"{staff.get_role_display()}. Temporary password: {temp_password} "
                "— share this with them directly; there's no self-service reset yet.",
            )
        else:
            messages.success(request, f"{user.name} assigned as {staff.get_role_display()}.")
        return redirect("adminpanel:committee_detail", pk=committee.pk)


class DelegateToggleActiveView(CommitteeAdminRequiredMixin, View):
    def post(self, request, pk):
        assignment = get_object_or_404(CountryAssignment, pk=pk)
        _require_committee_access(request.user, assignment.committee)
        assignment.is_active = not assignment.is_active
        assignment.save(update_fields=["is_active"])
        AuditLog.record(
            request.user, "delegate_toggled_active", assignment, is_active=assignment.is_active
        )
        messages.success(
            request,
            f"{assignment.country_name} is now "
            f"{'active' if assignment.is_active else 'inactive'}.",
        )
        return redirect("adminpanel:committee_detail", pk=assignment.committee.pk)


class StaffToggleActiveView(CommitteeAdminRequiredMixin, View):
    def post(self, request, pk):
        staff = get_object_or_404(CommitteeStaff, pk=pk)
        _require_committee_access(request.user, staff.committee)
        staff.is_active = not staff.is_active
        staff.save(update_fields=["is_active"])
        AuditLog.record(request.user, "staff_toggled_active", staff, is_active=staff.is_active)
        messages.success(
            request, f"{staff.user.name} is now {'active' if staff.is_active else 'inactive'}."
        )
        return redirect("adminpanel:committee_detail", pk=staff.committee.pk)


def _apply_admin_chit_filters(qs, get_params):
    conference_id = get_params.get("conference")
    committee_id = get_params.get("committee")
    status = get_params.get("status")
    category = get_params.get("category")
    via_eb = get_params.get("via_eb")
    q = get_params.get("q")

    if conference_id:
        qs = qs.filter(conference_id=conference_id)
    if committee_id:
        qs = qs.filter(committee_id=committee_id)
    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category=category)
    if via_eb:
        qs = qs.filter(is_via_eb=True)
    if q:
        qs = qs.filter(Q(subject__icontains=q) | Q(chit_number__icontains=q))
    return qs


class AdminChitListView(CommitteeAdminRequiredMixin, ListView):
    """
    Chit oversight across every conference the admin manages. Row-level
    read access mirrors Chit.objects.visible_to() for committee admins
    (all chits in their managed conferences) — scoping here starts from
    the same `managed_conferences_for(user)` helper used everywhere else
    in this app, so there's one source of truth for "what can this admin
    see," not a second parallel implementation.
    """

    template_name = "adminpanel/chit_list.html"
    context_object_name = "chits"
    paginate_by = 25

    def base_queryset(self):
        conferences = managed_conferences_for(self.request.user)
        return Chit.objects.filter(conference__in=conferences).select_related(
            "conference", "committee", "sender", "sender_country", "recipient_country"
        )

    def get_queryset(self):
        qs = self.base_queryset().order_by("-created_at")
        return _apply_admin_chit_filters(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["conferences"] = managed_conferences_for(user)
        context["committees"] = managed_committees_for(user)
        context["status_choices"] = Status.choices
        context["category_choices"] = Category.choices
        context["current_filters"] = {
            "conference": self.request.GET.get("conference", ""),
            "committee": self.request.GET.get("committee", ""),
            "status": self.request.GET.get("status", ""),
            "category": self.request.GET.get("category", ""),
            "via_eb": self.request.GET.get("via_eb", ""),
            "q": self.request.GET.get("q", ""),
        }
        return context


class AdminChitExportView(CommitteeAdminRequiredMixin, View):
    """
    Streams a CSV of every chit matching the same filters as the list
    view. Includes subject/message content — the requesting admin
    already has full read access to that content via visible_to(), so
    withholding it from the export while allowing it on-screen would be
    inconsistent, not safer. Whoever downloads this file is responsible
    for handling it as the private communication data it is.
    """

    def get(self, request):
        conferences = managed_conferences_for(request.user)
        qs = Chit.objects.filter(conference__in=conferences).select_related(
            "conference", "committee", "sender", "sender_country", "recipient_country"
        ).order_by("-created_at")
        qs = _apply_admin_chit_filters(qs, request.GET)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="chits_export.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "chit_number", "conference", "committee", "sender_country", "recipient_type",
                "recipient", "via_eb", "category", "status", "subject", "message",
                "is_anonymous", "created_at", "submitted_at",
            ]
        )
        for chit in qs:
            recipient = (
                "Executive Board"
                if chit.recipient_type == "executive_board"
                else (chit.recipient_country.country_name if chit.recipient_country else "")
            )
            writer.writerow(
                [
                    chit.chit_number,
                    chit.conference.name,
                    chit.committee.name,
                    chit.sender_country.country_name if chit.sender_country else "",
                    chit.get_recipient_type_display(),
                    recipient,
                    chit.is_via_eb,
                    chit.get_category_display(),
                    chit.get_status_display(),
                    chit.subject,
                    chit.message,
                    chit.is_anonymous,
                    chit.created_at.isoformat(),
                    chit.submitted_at.isoformat() if chit.submitted_at else "",
                ]
            )
        AuditLog.record(request.user, "chits_exported", Chit, count=qs.count())
        return response


class AuditLogListView(SuperAdminRequiredMixin, ListView):
    """
    Super Admin only. AuditLog entries aren't scoped to a conference (the
    model deliberately stores only generic object_type/object_id, never a
    conference FK), so there's no safe way to show a Committee Admin only
    "their" entries without unreliable metadata parsing — rather than
    build that on shaky ground, the full log is restricted to Super
    Admins for now.
    """

    model = AuditLog
    template_name = "adminpanel/audit_log_list.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor").all()
        action = self.request.GET.get("action")
        object_type = self.request.GET.get("object_type")
        if action:
            qs = qs.filter(action=action)
        if object_type:
            qs = qs.filter(object_type=object_type)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_choices"] = (
            AuditLog.objects.order_by().values_list("action", flat=True).distinct()
        )
        context["object_type_choices"] = (
            AuditLog.objects.order_by().values_list("object_type", flat=True).distinct()
        )
        context["current_filters"] = {
            "action": self.request.GET.get("action", ""),
            "object_type": self.request.GET.get("object_type", ""),
        }
        return context
