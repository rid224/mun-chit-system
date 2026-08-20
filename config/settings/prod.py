from .base import *  # noqa

DEBUG = False

# ALLOWED_HOSTS must be explicitly set via env var in production.
if not env.list("DJANGO_ALLOWED_HOSTS", default=[]):
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set in production")

# --- HTTPS / cookie hardening -------------------------------------------
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if SECRET_KEY == "dev-insecure-key-change-me":  # noqa
    raise RuntimeError("DJANGO_SECRET_KEY must be set via environment in production")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
