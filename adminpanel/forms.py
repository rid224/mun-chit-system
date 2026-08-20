from django import forms
from django.contrib.auth import get_user_model

from committees.models import Committee, CommitteeStaff, CountryAssignment
from conferences.models import Conference, Room

User = get_user_model()


class ConferenceForm(forms.ModelForm):
    class Meta:
        model = Conference
        fields = [
            "name",
            "year",
            "venue",
            "start_date",
            "end_date",
            "timezone",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "year": forms.NumberInput(attrs={"class": "form-control"}),
            "venue": forms.TextInput(attrs={"class": "form-control"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "timezone": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ConferenceSettingsForm(forms.ModelForm):
    class Meta:
        model = Conference
        fields = [
            "chit_submissions_enabled",
            "delegate_to_eb_enabled",
            "anonymous_chits_enabled",
            "replies_enabled",
            "cross_committee_chits_enabled",
            "max_message_length",
        ]
        widgets = {
            "chit_submissions_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "delegate_to_eb_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "anonymous_chits_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "replies_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "cross_committee_chits_enabled": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "max_message_length": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def clean_max_message_length(self):
        value = self.cleaned_data["max_message_length"]
        if value < 1 or value > 2000:
            raise forms.ValidationError("Must be between 1 and 2000 characters.")
        return value


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["name", "location", "capacity", "meeting_link", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "capacity": forms.NumberInput(attrs={"class": "form-control"}),
            "meeting_link": forms.URLInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CommitteeForm(forms.ModelForm):
    class Meta:
        model = Committee
        fields = [
            "name",
            "abbreviation",
            "committee_type",
            "room",
            "description",
            "is_active",
            "allow_cross_committee_chits",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "abbreviation": forms.TextInput(attrs={"class": "form-control"}),
            "committee_type": forms.Select(attrs={"class": "form-select"}),
            "room": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "allow_cross_committee_chits": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, conference, **kwargs):
        super().__init__(*args, **kwargs)
        self.conference = conference
        self.fields["room"].queryset = Room.objects.filter(conference=conference)
        self.fields["room"].required = False


class DelegateAssignForm(forms.Form):
    """
    Assigns a delegate to represent a country in a committee. If the email
    doesn't match an existing account, a new delegate User is created with
    a randomly generated temporary password — there's no self-service
    invite/reset flow yet, so the admin is shown that password once and is
    responsible for relaying it to the delegate out of band.
    """

    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    name = forms.CharField(
        required=False,
        help_text="Required only if this email doesn't already have an account.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    country_name = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    country_code = forms.CharField(
        max_length=8,
        widget=forms.TextInput(attrs={"class": "form-control", "maxlength": 8}),
    )

    def __init__(self, *args, committee, **kwargs):
        super().__init__(*args, **kwargs)
        self.committee = committee

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        name = cleaned_data.get("name")
        if email and not User.objects.filter(email__iexact=email).exists() and not name:
            self.add_error("name", "Enter a name to create a new account for this email.")

        country_code = cleaned_data.get("country_code")
        if country_code:
            cleaned_data["country_code"] = country_code.strip().upper()
            existing = CountryAssignment.objects.filter(
                committee=self.committee,
                country_code=cleaned_data["country_code"],
                is_active=True,
            )
            if existing.exists():
                self.add_error(
                    "country_code",
                    "This country is already actively represented in this committee.",
                )
        return cleaned_data


class CommitteeStaffAssignForm(forms.Form):
    """Assigns an Executive Board role. Same create-or-link-by-email behavior as delegates."""

    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    name = forms.CharField(
        required=False,
        help_text="Required only if this email doesn't already have an account.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    role = forms.ChoiceField(
        choices=CommitteeStaff.StaffRole.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, committee, **kwargs):
        super().__init__(*args, **kwargs)
        self.committee = committee

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        name = cleaned_data.get("name")
        if email and not User.objects.filter(email__iexact=email).exists() and not name:
            self.add_error("name", "Enter a name to create a new account for this email.")
        return cleaned_data
