from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Relaxed cookie security for local HTTP development only.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
