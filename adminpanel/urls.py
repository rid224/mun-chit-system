from django.urls import path

from . import views

app_name = "adminpanel"

urlpatterns = [
    path("dashboard/", views.AdminDashboardView.as_view(), name="dashboard"),

    path("conferences/", views.ConferenceListView.as_view(), name="conference_list"),
    path("conferences/create/", views.ConferenceCreateView.as_view(), name="conference_create"),
    path("conferences/<uuid:pk>/", views.ConferenceDetailView.as_view(), name="conference_detail"),
    path("conferences/<uuid:pk>/edit/", views.ConferenceEditView.as_view(), name="conference_edit"),
    path(
        "conferences/<uuid:pk>/settings/",
        views.ConferenceSettingsView.as_view(),
        name="conference_settings",
    ),

    path(
        "conferences/<uuid:conference_pk>/rooms/create/",
        views.RoomCreateView.as_view(),
        name="room_create",
    ),
    path("rooms/<uuid:pk>/edit/", views.RoomEditView.as_view(), name="room_edit"),
    path(
        "rooms/<uuid:pk>/toggle-active/",
        views.RoomToggleActiveView.as_view(),
        name="room_toggle_active",
    ),

    path(
        "conferences/<uuid:conference_pk>/committees/create/",
        views.CommitteeCreateView.as_view(),
        name="committee_create",
    ),
    path("committees/<uuid:pk>/edit/", views.CommitteeEditView.as_view(), name="committee_edit"),
    path(
        "committees/<uuid:pk>/toggle-active/",
        views.CommitteeToggleActiveView.as_view(),
        name="committee_toggle_active",
    ),
    path("committees/<uuid:pk>/", views.CommitteeDetailView.as_view(), name="committee_detail"),

    path(
        "committees/<uuid:committee_pk>/delegates/assign/",
        views.DelegateAssignView.as_view(),
        name="delegate_assign",
    ),
    path(
        "delegates/<uuid:pk>/toggle-active/",
        views.DelegateToggleActiveView.as_view(),
        name="delegate_toggle_active",
    ),
    path(
        "committees/<uuid:committee_pk>/staff/assign/",
        views.CommitteeStaffAssignView.as_view(),
        name="staff_assign",
    ),
    path(
        "staff/<uuid:pk>/toggle-active/",
        views.StaffToggleActiveView.as_view(),
        name="staff_toggle_active",
    ),

    path("chits/", views.AdminChitListView.as_view(), name="chit_list"),
    path("chits/export/", views.AdminChitExportView.as_view(), name="chit_export"),

    path("audit-log/", views.AuditLogListView.as_view(), name="audit_log"),
]
