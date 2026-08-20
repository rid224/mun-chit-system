from django.contrib import admin

from .models import Committee, CommitteeStaff, CountryAssignment


class CountryAssignmentInline(admin.TabularInline):
    model = CountryAssignment
    extra = 0


class CommitteeStaffInline(admin.TabularInline):
    model = CommitteeStaff
    extra = 0


@admin.register(Committee)
class CommitteeAdmin(admin.ModelAdmin):
    list_display = ["name", "conference", "committee_type", "room", "is_active"]
    list_filter = ["conference", "committee_type", "is_active"]
    search_fields = ["name", "abbreviation"]
    inlines = [CountryAssignmentInline, CommitteeStaffInline]


@admin.register(CountryAssignment)
class CountryAssignmentAdmin(admin.ModelAdmin):
    list_display = ["country_name", "country_code", "committee", "user", "is_active"]
    list_filter = ["committee__conference", "committee", "is_active"]
    search_fields = ["country_name", "country_code", "user__email", "user__name"]


@admin.register(CommitteeStaff)
class CommitteeStaffAdmin(admin.ModelAdmin):
    list_display = ["user", "committee", "role", "is_active"]
    list_filter = ["committee__conference", "committee", "role", "is_active"]
    search_fields = ["user__email", "user__name"]
