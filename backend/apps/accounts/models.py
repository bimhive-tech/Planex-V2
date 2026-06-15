"""Multi-tenant auth models: Company (tenant), User, Department, Role, Membership.

Tenant isolation rule: every tenant-owned row carries a company FK and is always
filtered by the request user's company (except the platform-admin company, which
may act across companies). UUID PKs everywhere that may appear in a URL.
"""
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.text import slugify

from .constants import Permission


class TimestampedModel(models.Model):
    """Adds created_at / updated_at to every model."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Company(TimestampedModel):
    """A tenant. The single `is_platform_admin` company owns the platform itself."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    is_platform_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Optional company profile (shown/edited on the Settings → Info tab).
    phone_number = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    website = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.name) or "company"
        slug, i = base, 1
        while Company.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            i += 1
            slug = f"{base}-{i}"
        return slug


class UserManager(BaseUserManager):
    """Email-based user manager (no username field)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_staff and is_superuser = True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    """Custom user. Logs in with email; belongs to exactly one company."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=40, blank=True)

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="users", null=True, blank=True
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django-admin access
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email + password handled by manager

    class Meta:
        ordering = ["email"]
        indexes = [models.Index(fields=["company", "is_active"])]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def is_platform_admin(self):
        """True when the user belongs to the administrative company."""
        return bool(self.company and self.company.is_platform_admin)

    def effective_permissions(self):
        """Union of permission keys across the user's active memberships.

        Platform-admin company users implicitly hold every permission.
        """
        if self.is_platform_admin:
            return set(p.value for p in Permission)
        perms: set[str] = set()
        for membership in self.memberships.filter(is_active=True).select_related("role"):
            perms.update(membership.role.permissions or [])
        return perms


class Department(TimestampedModel):
    """Company-scoped organizational group."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_department_per_company")
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Role(TimestampedModel):
    """Company-scoped role carrying a set of action-permission keys."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=120)
    is_platform_role = models.BooleanField(default=False)
    permissions = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_role_per_company")
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class Membership(TimestampedModel):
    """Assigns a user a role (and optional department) within a company."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="memberships"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "user", "role", "department"],
                name="uniq_membership",
            )
        ]
        indexes = [models.Index(fields=["company", "user"])]

    def __str__(self):
        return f"{self.user.email} · {self.role.name}"
