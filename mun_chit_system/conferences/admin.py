from django.contrib import admin

from .models import Conference, Room


class RoomInline(admin.TabularInline):
    model = Room
    extra = 0


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ["name", "year", "is_active", "start_date", "end_date"]
    list_filter = ["is_active", "year"]
    search_fields = ["name", "venue"]
    inlines = [RoomInline]


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["name", "conference", "capacity", "is_active"]
    list_filter = ["conference", "is_active"]
    search_fields = ["name", "location"]
