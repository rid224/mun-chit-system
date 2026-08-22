from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from accounts.permissions import DelegateRequiredMixin, ExecutiveBoardRequiredMixin
from committees.models import Committee, CountryAssignment
from committees.selectors import get_committee_context

from .forms import ReplyForm, SendChitForm
from .models import Category, Chit, ChitReply, RecipientType, Status


class ActiveCommitteeMixin:
    """
    Resolves request.session['active_committee_id'] into a real, currently
    valid Committee + role context for this user, re-checked against live
    assignment records on every request. If the session value is missing,
    stale, or the user no longer has standing there, bounce back through
    the dashboard redirect (which will re-run committee selection).
    """

    required_role = None  # "delegate" or "executive_board"

    def dispatch(self, request, *args, **kwargs):
        committee_id = request.session.get("active_committee_id")
        if not committee_id:
            return redirect("accounts:dashboard_redirect")

        try:
            committee = Committee.objects.select_related("conference", "room").get(
                id=committee_id
            )
        except (Committee.DoesNotExist, ValueError):
            return redirect("accounts:dashboard_redirect")

        context = get_committee_context(request.user, committee)
        if context is None or (self.required_role and context["role"] != self.required_role):
            return redirect("accounts:dashboard_redirect")

        self.active_committee = committee
        self.committee_context = context
        return super().dispatch(request, *args, **kwargs)


class DelegateDashboardView(DelegateRequiredMixin, ActiveCommitteeMixin, TemplateView):
    required_role = "delegate"
    template_name = "chits/delegate_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["committee"] = self.active_committee
        context["assignment"] = self.committee_context["assignment"]
        context["sent_count"] = Chit.objects.visible_to(self.request.user).filter(
            sender=self.request.user
        ).count()
        context["received_count"] = Chit.objects.visible_to(self.request.user).exclude(
            sender=self.request.user
        ).count()
        return context


class ChitListFilterMixin:
    """Shared search/filter/pagination logic for the sent and received lists."""

    paginate_by = 15

    def apply_filters(self, qs):
        request = self.request
        status = request.GET.get("status")
        category = request.GET.get("category")
        q = request.GET.get("q")

        if status:
            qs = qs.filter(status=status)
        if category:
            qs = qs.filter(category=category)
        if q:
            qs = qs.filter(Q(subject__icontains=q) | Q(chit_number__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["committee"] = self.active_committee
        context["status_choices"] = Status.choices
        context["category_choices"] = Category.choices
        context["current_filters"] = {
            "status": self.request.GET.get("status", ""),
            "category": self.request.GET.get("category", ""),
            "q": self.request.GET.get("q", ""),
        }
        return context


class EBDashboardView(ExecutiveBoardRequiredMixin, ActiveCommitteeMixin, TemplateView):
    required_role = "executive_board"
    template_name = "chits/eb_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["committee"] = self.active_committee
        visible = Chit.objects.visible_to(self.request.user).filter(
            committee=self.active_committee
        ).exclude(status=Status.ARCHIVED)
        context["new_count"] = visible.filter(status=Status.SUBMITTED).count()
        context["unread_count"] = visible.unread().count()
        context["awaiting_response_count"] = visible.awaiting_response().count()
        return context


class EBIncomingChitsView(
    ExecutiveBoardRequiredMixin, ActiveCommitteeMixin, ChitListFilterMixin, ListView
):
    """
    Combines the New / Unread / Awaiting-response queues required by the
    spec into one filterable inbox (?queue=new|unread|awaiting), plus the
    same search/status/category filters as delegate history views.
    Archived chits are excluded here — see EBArchiveView. Also includes
    delegate-to-delegate chits explicitly CC'd "Via EB" (see
    Chit.is_via_eb) — those come through automatically via
    Chit.objects.visible_to(), so no separate handling is needed here.
    """

    required_role = "executive_board"
    template_name = "chits/eb_incoming.html"
    context_object_name = "chits"

    def base_queryset(self):
        return (
            Chit.objects.visible_to(self.request.user)
            .filter(committee=self.active_committee)
            .exclude(status=Status.ARCHIVED)
        )

    def get_queryset(self):
        qs = self.base_queryset().order_by("-created_at")
        queue = self.request.GET.get("queue", "all")
        if queue == "new":
            qs = qs.filter(status=Status.SUBMITTED)
        elif queue == "unread":
            qs = qs.unread()
        elif queue == "awaiting":
            qs = qs.awaiting_response()
        return self.apply_filters(qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = self.base_queryset()
        queue = self.request.GET.get("queue", "all")
        counts = {
            "all": base.count(),
            "new": base.filter(status=Status.SUBMITTED).count(),
            "unread": base.unread().count(),
            "awaiting": base.awaiting_response().count(),
        }
        context["queue"] = queue
        context["queue_counts"] = counts
        context["queue_tabs"] = [
            ("all", "All", counts["all"]),
            ("new", "New", counts["new"]),
            ("unread", "Unread", counts["unread"]),
            ("awaiting", "Awaiting response", counts["awaiting"]),
        ]
        return context


class EBArchiveView(
    ExecutiveBoardRequiredMixin, ActiveCommitteeMixin, ChitListFilterMixin, ListView
):
    required_role = "executive_board"
    template_name = "chits/eb_archive.html"
    context_object_name = "chits"

    def get_queryset(self):
        qs = (
            Chit.objects.visible_to(self.request.user)
            .filter(committee=self.active_committee, status=Status.ARCHIVED)
            .order_by("-archived_at")
        )
        return self.apply_filters(qs)


class SendChitView(DelegateRequiredMixin, ActiveCommitteeMixin, View):
    """
    Step 1 of 2. Validates the compose form server-side and stashes the
    validated data in the session as a draft — nothing is written to the
    database until the user confirms on the preview screen.
    """

    required_role = "delegate"
    template_name = "chits/send.html"

    def get(self, request, *args, **kwargs):
        form = self._build_form(initial=request.session.get("chit_draft"))
        return render(request, self.template_name, self._context(form))

    def post(self, request, *args, **kwargs):
        form = self._build_form(data=request.POST)
        if form.is_valid():
            request.session["chit_draft"] = self._serialize(form.cleaned_data)
            return redirect("chits:preview")
        return render(request, self.template_name, self._context(form))

    def _sender_assignment(self):
        return self.committee_context["assignment"]

    def _build_form(self, data=None, initial=None):
        form_kwargs = {
            "committee": self.active_committee,
            "sender_assignment": self._sender_assignment(),
        }
        if data is not None:
            return SendChitForm(data, **form_kwargs)

        init = {}
        if initial:
            init = {
                "recipient_type": initial.get("recipient_type"),
                "recipient_country": initial.get("recipient_country_id"),
                "is_via_eb": initial.get("is_via_eb"),
                "subject": initial.get("subject"),
                "message": initial.get("message"),
                "category": initial.get("category"),
                "is_anonymous": initial.get("is_anonymous"),
            }
        return SendChitForm(initial=init, **form_kwargs)

    @staticmethod
    def _serialize(cleaned):
        recipient_country = cleaned.get("recipient_country")
        return {
            "recipient_type": cleaned["recipient_type"],
            "recipient_country_id": str(recipient_country.id) if recipient_country else None,
            "is_via_eb": cleaned.get("is_via_eb", False),
            "subject": cleaned.get("subject", ""),
            "message": cleaned["message"],
            "category": cleaned["category"],
            "is_anonymous": cleaned.get("is_anonymous", False),
        }

    def _context(self, form):
        return {
            "form": form,
            "committee": self.active_committee,
            "max_length": getattr(form, "effective_max_length", None),
        }


class PreviewChitView(DelegateRequiredMixin, ActiveCommitteeMixin, View):
    """
    Step 2 of 2. Shows a read-only preview of the draft, re-validates it
    live (in case anything changed since compose — a recipient going
    inactive, submissions being disabled, etc.), then creates the Chit on
    confirmation. Template rendering relies on Django's default
    autoescaping for the subject/message fields — no |safe filter is used
    anywhere near user-generated chit content.
    """

    required_role = "delegate"
    template_name = "chits/preview.html"

    def get(self, request, *args, **kwargs):
        draft = request.session.get("chit_draft")
        if not draft:
            messages.info(request, "Start by composing your chit.")
            return redirect("chits:send")

        context = self._preview_context(draft)
        if context is None:
            del request.session["chit_draft"]
            messages.error(
                request, "Your draft is no longer valid — please compose it again."
            )
            return redirect("chits:send")
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        draft = request.session.get("chit_draft")
        if not draft:
            return redirect("chits:send")

        sender_assignment = self.committee_context["assignment"]
        form = SendChitForm(
            self._draft_as_post_data(draft),
            committee=self.active_committee,
            sender_assignment=sender_assignment,
        )
        if not form.is_valid():
            del request.session["chit_draft"]
            messages.error(
                request,
                "Something changed since you composed this chit "
                "(a setting or recipient may no longer be valid). Please review and resend.",
            )
            return redirect("chits:send")

        cleaned = form.cleaned_data
        chit = Chit(
            conference=self.active_committee.conference,
            committee=self.active_committee,
            room=self.active_committee.room,
            sender=request.user,
            sender_country=sender_assignment,
            recipient_country=cleaned.get("recipient_country"),
            recipient_type=cleaned["recipient_type"],
            is_via_eb=cleaned.get("is_via_eb", False),
            subject=cleaned.get("subject", ""),
            message=cleaned["message"],
            category=cleaned["category"],
            is_anonymous=cleaned.get("is_anonymous", False),
            status=Status.SUBMITTED,
            submitted_at=timezone.now(),
        )
        chit.full_clean()
        chit.save()

        del request.session["chit_draft"]
        messages.success(request, f"Chit {chit.chit_number} sent.")
        return redirect("chits:detail", public_id=chit.public_id)

    @staticmethod
    def _draft_as_post_data(draft):
        data = QueryDict(mutable=True)
        data.update(
            {
                "recipient_type": draft["recipient_type"],
                "recipient_country": draft.get("recipient_country_id") or "",
                "is_via_eb": "on" if draft.get("is_via_eb") else "",
                "subject": draft.get("subject", ""),
                "message": draft["message"],
                "category": draft["category"],
                "is_anonymous": "on" if draft.get("is_anonymous") else "",
                "agree_to_rules": "on",  # confirmed at the compose step already
            }
        )
        return data

    def _preview_context(self, draft):
        recipient_country = None
        if draft.get("recipient_country_id"):
            try:
                # Not scoped to `committee=self.active_committee` here —
                # a cross-committee recipient (see SendChitForm) is valid
                # even though they're in a different committee. This is
                # just for display; the authoritative re-validation
                # (including whether cross-committee is actually allowed)
                # happens in post() via SendChitForm.clean().
                recipient_country = CountryAssignment.objects.get(
                    pk=draft["recipient_country_id"],
                    is_active=True,
                )
            except (CountryAssignment.DoesNotExist, ValueError):
                return None

        return {
            "committee": self.active_committee,
            "draft": draft,
            "recipient_country": recipient_country,
            "category_display": dict(Category.choices).get(draft["category"], draft["category"]),
        }


class SentChitsView(DelegateRequiredMixin, ActiveCommitteeMixin, ChitListFilterMixin, ListView):
    required_role = "delegate"
    template_name = "chits/sent_list.html"
    context_object_name = "chits"

    def get_queryset(self):
        qs = (
            Chit.objects.visible_to(self.request.user)
            .filter(sender=self.request.user, committee=self.active_committee)
            .select_related("recipient_country")
            .order_by("-created_at")
        )
        return self.apply_filters(qs)


class ReceivedChitsView(DelegateRequiredMixin, ActiveCommitteeMixin, ChitListFilterMixin, ListView):
    required_role = "delegate"
    template_name = "chits/received_list.html"
    context_object_name = "chits"

    def get_queryset(self):
        # Scoped by the RECIPIENT's country assignment committee, not the
        # chit's own `committee` field (which records where the chit was
        # sent FROM). For an ordinary same-committee chit these are always
        # equal, but for a cross-committee chit (see SendChitForm) they
        # differ — filtering on `committee=` here would silently hide
        # incoming cross-committee chits from the recipient's own
        # committee-scoped inbox even though visible_to() correctly grants
        # them read access via the detail page.
        qs = (
            Chit.objects.visible_to(self.request.user)
            .exclude(sender=self.request.user)
            .filter(recipient_country__committee=self.active_committee)
            .select_related("sender_country")
            .order_by("-created_at")
        )
        return self.apply_filters(qs)


class ChitDetailView(LoginRequiredMixin, DetailView):
    """
    Read access is governed entirely by Chit.objects.visible_to(user) — not
    by the currently active committee — since a user's own chit history
    shouldn't disappear from view just because they've since switched their
    active committee via the selector.
    """

    model = Chit
    template_name = "chits/detail.html"
    context_object_name = "chit"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"

    def get_queryset(self):
        return (
            Chit.objects.visible_to(self.request.user)
            .select_related("sender", "recipient_country", "committee", "room", "conference")
            .prefetch_related("replies__author")
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self._mark_delivered_and_read_if_recipient(self.object)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        chit = self.object

        action = request.POST.get("action")
        if action == "reply":
            if not self._is_delegate_party(chit):
                raise PermissionDenied(
                    "Only the sender or recipient delegate of this chit can reply to it."
                )
            return self._handle_reply(request, chit)
        if action == "archive":
            if not self._is_eb_actor(chit):
                raise PermissionDenied("Only the Executive Board of this committee can do that.")
            return self._handle_archive(request, chit)
        return redirect("chits:detail", public_id=chit.public_id)

    def _is_delegate_party(self, chit):
        """
        True only for the two delegates actually party to this chit — the
        sender, or the addressed recipient country's delegate. Only
        meaningful for delegate-to-delegate chits (recipient_type ==
        DELEGATE); a chit addressed directly to the Executive Board has no
        "recipient delegate" to grant this to.
        """
        if chit.recipient_type != RecipientType.DELEGATE:
            return False
        user = self.request.user
        is_sender = chit.sender_id == user.id
        is_recipient = bool(
            chit.recipient_country_id and chit.recipient_country.user_id == user.id
        )
        return is_sender or is_recipient

    def _is_eb_actor(self, chit):
        """True only if the current user is an active EB member of THIS
        chit's committee AND the chit is either addressed directly to the
        EB, or is a delegate-to-delegate chit explicitly CC'd "Via EB" —
        checked server-side on every POST, never inferred from the UI.
        Note: EB no longer has reply permission (moved to the delegate
        parties themselves) — this now only gates the archive action and
        general visibility/read-receipt logic."""
        is_eb_addressed = chit.recipient_type == RecipientType.EXECUTIVE_BOARD
        is_via_eb_delegate_chit = (
            chit.recipient_type == RecipientType.DELEGATE and chit.is_via_eb
        )
        if not (is_eb_addressed or is_via_eb_delegate_chit):
            return False
        context = get_committee_context(self.request.user, chit.committee)
        return context is not None and context["role"] == "executive_board"

    def _handle_reply(self, request, chit):
        if not chit.conference.replies_enabled:
            messages.error(request, "Replies are currently disabled for this conference.")
            return redirect("chits:detail", public_id=chit.public_id)
        if chit.status == Status.ARCHIVED:
            messages.error(request, "This chit is archived and can no longer be replied to.")
            return redirect("chits:detail", public_id=chit.public_id)

        form = ReplyForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Reply could not be sent — check the message and try again.")
            return redirect("chits:detail", public_id=chit.public_id)

        ChitReply.objects.create(
            chit=chit, author=request.user, message=form.cleaned_data["message"]
        )
        chit.status = Status.REPLIED
        chit.replied_at = timezone.now()
        chit.save(update_fields=["status", "replied_at"])
        messages.success(request, "Reply sent.")
        return redirect("chits:detail", public_id=chit.public_id)

    def _handle_archive(self, request, chit):
        if chit.status == Status.ARCHIVED:
            return redirect("chits:detail", public_id=chit.public_id)
        chit.status = Status.ARCHIVED
        chit.archived_at = timezone.now()
        chit.save(update_fields=["status", "archived_at"])
        messages.success(request, f"{chit.chit_number} archived.")
        return redirect("chits:eb_incoming")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        chit = context["object"]
        context["is_eb_actor"] = self._is_eb_actor(chit)
        context["is_delegate_party"] = self._is_delegate_party(chit)
        context["reply_form"] = ReplyForm()
        return context

    def _mark_delivered_and_read_if_recipient(self, chit):
        """
        A direct delegate recipient, or an EB member of the addressed
        committee, viewing the chit transitions it
        Submitted -> Delivered -> Read. Only applies to the actual
        addressee — a sender viewing their own sent chit, or an unrelated
        user landing here via visible_to() for another reason, never
        mutates status.
        """
        user = self.request.user
        is_recipient_delegate = (
            chit.recipient_type == RecipientType.DELEGATE
            and chit.recipient_country_id
            and chit.recipient_country.user_id == user.id
        )
        is_recipient_eb = chit.recipient_type == RecipientType.EXECUTIVE_BOARD and self._is_eb_actor(
            chit
        )
        if not (is_recipient_delegate or is_recipient_eb):
            return

        now = timezone.now()
        changed_fields = []
        if chit.status == Status.SUBMITTED:
            chit.delivered_at = chit.delivered_at or now
            chit.status = Status.DELIVERED
            changed_fields += ["status", "delivered_at"]
        if chit.status == Status.DELIVERED:
            chit.read_at = chit.read_at or now
            chit.status = Status.READ
            changed_fields += ["status", "read_at"]
        if changed_fields:
            chit.save(update_fields=list(dict.fromkeys(changed_fields)))
