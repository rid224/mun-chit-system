from django.urls import path

from . import views

app_name = "chits"

urlpatterns = [
    path("delegate/dashboard/", views.DelegateDashboardView.as_view(), name="delegate_dashboard"),
    path("delegate/send/", views.SendChitView.as_view(), name="send"),
    path("delegate/send/preview/", views.PreviewChitView.as_view(), name="preview"),
    path("delegate/sent/", views.SentChitsView.as_view(), name="sent"),
    path("delegate/received/", views.ReceivedChitsView.as_view(), name="received"),
    path("chits/<uuid:public_id>/", views.ChitDetailView.as_view(), name="detail"),
    path("eb/dashboard/", views.EBDashboardView.as_view(), name="eb_dashboard"),
    path("eb/incoming/", views.EBIncomingChitsView.as_view(), name="eb_incoming"),
    path("eb/archive/", views.EBArchiveView.as_view(), name="eb_archive"),
]
