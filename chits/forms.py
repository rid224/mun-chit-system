from django import forms

from committees.models import CountryAssignment

from .models import MAX_MESSAGE_LENGTH, Category, RecipientType


class SendChitForm(forms.Form):
    """
    Validates a delegate's chit submission. Committee, room, and sender are
    NEVER fields on this form — they're resolved server-side by the view
    from the live active-committee session context and passed into
    __init__, so a delegate cannot submit a chit under a different
    committee than the one they're actually assigned to.
    """

    recipient_type = forms.ChoiceField(
        choices=[
            (RecipientType.DELEGATE, "A delegate (by country)"),
            (RecipientType.EXECUTIVE_BOARD, "The Executive Board"),
        ],
        widget=forms.RadioSelect,
    )
    recipient_country = forms.ModelChoiceField(
        queryset=CountryAssignment.objects.none(),
        required=False,
        empty_label="Select a country…",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    is_via_eb = forms.BooleanField(
        required=False,
        label="Also send a copy to the Executive Board (Via EB)",
        help_text=(
            "The committee's Executive Board will be able to read this chit "
            "and its replies, and may reply themselves."
        ),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    subject = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "maxlength": 200}),
    )
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 6,
                "id": "id_message",
                "aria-describedby": "char-count-help",
            }
        ),
    )
    category = forms.ChoiceField(
        choices=Category.choices, widget=forms.Select(attrs={"class": "form-select"})
    )
    is_anonymous = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )
    agree_to_rules = forms.BooleanField(
        required=True,
        label="I confirm this chit follows conference rules and code of conduct.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, committee, sender_assignment, **kwargs):
        super().__init__(*args, **kwargs)
        self.committee = committee
        self.conference = committee.conference
        self.sender_assignment = sender_assignment
        self.cross_committee_allowed = bool(
            committee.allow_cross_committee_chits and self.conference.cross_committee_chits_enabled
        )

        # Recipients are limited to active delegates in the SAME committee,
        # excluding the sender's own country assignment — UNLESS both the
        # committee and the conference have explicitly enabled
        # cross-committee chits, in which case any active delegate
        # elsewhere in the same conference becomes a valid recipient too.
        if self.cross_committee_allowed:
            recipient_qs = CountryAssignment.objects.filter(
                committee__conference=self.conference, is_active=True
            ).exclude(pk=sender_assignment.pk)
        else:
            recipient_qs = CountryAssignment.objects.filter(
                committee=committee, is_active=True
            ).exclude(pk=sender_assignment.pk)
        self.fields["recipient_country"].queryset = recipient_qs.select_related("committee")

        effective_max_length = min(self.conference.max_message_length, MAX_MESSAGE_LENGTH)
        self.effective_max_length = effective_max_length
        self.fields["message"].max_length = effective_max_length
        self.fields["message"].widget.attrs["maxlength"] = effective_max_length

        if not self.conference.anonymous_chits_enabled:
            del self.fields["is_anonymous"]

    def clean(self):
        cleaned_data = super().clean()

        if not self.conference.chit_submissions_enabled:
            raise forms.ValidationError(
                "Chit submissions are currently disabled for this conference."
            )

        recipient_type = cleaned_data.get("recipient_type")
        recipient_country = cleaned_data.get("recipient_country")

        if recipient_type == RecipientType.DELEGATE:
            if not recipient_country:
                self.add_error("recipient_country", "Choose which country to send this chit to.")
            elif recipient_country.pk == self.sender_assignment.pk:
                self.add_error("recipient_country", "You cannot send a chit to your own country.")
            elif recipient_country.committee_id != self.committee.id:
                # Defense in depth: the queryset already scopes this, but
                # never trust a submitted PK without re-checking
                # server-side — including re-checking the cross-committee
                # toggle itself, in case it changed between page load and
                # submission.
                if not self.cross_committee_allowed:
                    self.add_error("recipient_country", "Invalid recipient for this committee.")
                elif recipient_country.committee.conference_id != self.conference.id:
                    self.add_error("recipient_country", "Invalid recipient for this conference.")


        elif recipient_type == RecipientType.EXECUTIVE_BOARD:
            if not self.conference.delegate_to_eb_enabled:
                raise forms.ValidationError(
                    "Delegate-to-Executive-Board messages are currently disabled "
                    "for this conference."
                )
            cleaned_data["recipient_country"] = None
            # "Via EB" is meaningless when the chit is already addressed
            # directly to the EB — never trust a stray checked box here.
            cleaned_data["is_via_eb"] = False

        message = cleaned_data.get("message", "")
        if len(message) > self.effective_max_length:
            self.add_error(
                "message",
                f"Message exceeds the maximum length of {self.effective_max_length} characters.",
            )

        return cleaned_data


class ReplyForm(forms.Form):
    """Used by an Executive Board member replying to a chit addressed to their committee's EB."""

    message = forms.CharField(
        max_length=MAX_MESSAGE_LENGTH,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 4, "maxlength": MAX_MESSAGE_LENGTH}
        ),
    )
