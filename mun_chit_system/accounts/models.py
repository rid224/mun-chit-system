import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class Role(models.TextChoices):
    DELEGATE = "delegate", "Delegate"
    EXECUTIVE_BOARD = "executive_board", "Executive Board"
    COMMITTEE_ADMIN = "committee_admin", "Committee Administrator"
    SUPER_ADMIN = "super_admin", "Super Administrator"


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model, authenticated by email instead of username.
    Password is always stored hashed via Django's PBKDF2/argon2 machinery —
    never touched or stored in plaintext anywhere in this codebase.

    `role` is a denormalized convenience field for fast checks; the
    authoritative source of truth for *what a user can do* is still their
    CountryAssignment / CommitteeStaff / group membership records, checked
    at the queryset level (see committees.selectors and chits.querysets).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.DELEGATE)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    # Conferences a Committee Administrator manages. Irrelevant for other roles.
    managed_conferences = models.ManyToManyField(
        "conferences.Conference",
        blank=True,
        related_name="admins",
        help_text="Conferences this user administers (Committee Administrator role).",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    @property
    def is_delegate(self):
        return self.role == Role.DELEGATE

    @property
    def is_executive_board(self):
        return self.role == Role.EXECUTIVE_BOARD

    @property
    def is_committee_admin(self):
        return self.role == Role.COMMITTEE_ADMIN

    @property
    def is_super_admin(self):
        return self.role == Role.SUPER_ADMIN or self.is_superuser
