from django.contrib import admin

from .models import Chit, ChitReply


class ChitReplyInline(admin.TabularInline):
    model = ChitReply
    extra = 0
    readonly_fields = ["author", "created_at"]


@admin.register(Chit)
class ChitAdmin(admin.ModelAdmin):
    list_display = [
        "chit_number", "conference", "committee", "room", "sender",
        "recipient_type", "status", "priority", "created_at",
    ]
    list_filter = ["conference", "committee", "status", "priority", "recipient_type", "category"]
    search_fields = ["chit_number", "subject", "sender__email", "sender__name"]
    readonly_fields = ["public_id", "chit_number", "created_at"]
    inlines = [ChitReplyInline]
    date_hierarchy = "created_at"

    def has_change_permission(self, request, obj=None):
        # Admins can view/manage but message content stays read-only in list;
        # full edit still gated by Django's own object perms + our role checks.
        return request.user.is_superuser or getattr(request.user, "is_committee_admin", False)


@admin.register(ChitReply)
class ChitReplyAdmin(admin.ModelAdmin):
    list_display = ["chit", "author", "created_at"]
    search_fields = ["chit__chit_number", "author__email"]
