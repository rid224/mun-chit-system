from django.urls import path

from . import views

app_name = "committees"

urlpatterns = [
    path("select/", views.CommitteeSelectView.as_view(), name="select"),
]
