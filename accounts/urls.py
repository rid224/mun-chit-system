from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.LandingView.as_view(), name="landing"),
    path("login/", views.RateLimitedLoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("unauthorized/", views.UnauthorizedView.as_view(), name="unauthorized"),
    path("dashboard/", views.DashboardRedirectView.as_view(), name="dashboard_redirect"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
]
