"""Business logic for Master Data. Views delegate here — same shape as
apps.accounts.settings_services (thin views, logic in services).
"""
from django.db import transaction

from apps.accounts.models import Company

from .models import Currency, Party, ProjectPriority, ProjectType

# Every Project field the one party roster supplies. Deleting a row is blocked
# while any project still holds that name in ANY of them (see _party_in_use),
# same rule the other lists already follow.
#
# One tuple, not one per role: a party has no role of its own now, so "is this
# still in use?" and "carry this rename onto the projects using it" both have
# to look everywhere a name can be named. A firm renamed while it is a
# contractor on one project and a consultant on another must be renamed on
# both, or the second project's dropdown quietly goes blank.
_PARTY_PROJECT_FIELDS = (
    "client_name",
    "consultant_name",
    "contractor_consultant",
    "contractor_name",
    "subcontractor_name",
)

# The four project types and three priorities that already exist as Django
# TextChoices on Project (see apps.projects.models) — seeded verbatim (same
# lowercase values) so every existing Project's stored value still appears
# selected when its edit form opens, and Project.get_project_type_display()/
# get_priority_display() keep mapping them to their existing labels. A company
# is free to rename or delete these once seeded; only the *value* on an
# existing Project is ever left alone (it's just a string, never a FK).
_DEFAULT_PROJECT_TYPES = ["commercial", "residential", "infrastructure", "industrial"]
_DEFAULT_PRIORITIES = ["low", "medium", "high"]

# A small starting set of currencies. AED is Project.currency's own default,
# so it's the seeded default here too; USD/SAR/EGP cover the other codes
# already seen in this codebase's fixtures/reports.
_DEFAULT_CURRENCIES = [
    ("AED", "UAE Dirham", "", True),
    ("USD", "US Dollar", "$", False),
    ("SAR", "Saudi Riyal", "", False),
    ("EGP", "Egyptian Pound", "", False),
]


def seed_default_master_data(company: Company) -> None:
    """Give a company a sensible starting set of currencies/types/priorities.
    Idempotent (get_or_create), so it's safe to call on every company create
    and to replay for companies that already have some rows."""
    for i, code in enumerate(_DEFAULT_PROJECT_TYPES):
        ProjectType.objects.get_or_create(company=company, name=code, defaults={"sort_order": i})
    for i, name in enumerate(_DEFAULT_PRIORITIES):
        ProjectPriority.objects.get_or_create(company=company, name=name, defaults={"sort_order": i})
    for i, (code, name, symbol, is_default) in enumerate(_DEFAULT_CURRENCIES):
        Currency.objects.get_or_create(
            company=company, code=code,
            defaults={"name": name, "symbol": symbol, "is_default": is_default, "sort_order": i},
        )


class MasterDataError(Exception):
    """An expected, user-facing failure (duplicate code/name, still in use) —
    views turn this into a 400 rather than letting an IntegrityError 500."""


def _in_use_count(company: Company, *, field: str, value: str) -> int:
    from apps.projects.models import Project
    return Project.objects.filter(company=company, **{field: value}).count()


@transaction.atomic
def create_currency(*, company: Company, code: str, name: str, symbol: str, is_default: bool) -> Currency:
    code = code.strip().upper()
    if Currency.objects.filter(company=company, code=code).exists():
        raise MasterDataError(f"'{code}' already exists for this company.")
    currency = Currency.objects.create(
        company=company, code=code, name=name.strip(), symbol=symbol.strip(),
        is_default=False, sort_order=Currency.objects.filter(company=company).count(),
    )
    if is_default:
        set_default_currency(currency=currency)
    return currency


@transaction.atomic
def set_default_currency(*, currency: Currency) -> Currency:
    """Exactly one currency is default per company — flipping one on flips
    every other off in the same transaction."""
    Currency.objects.filter(company=currency.company).exclude(pk=currency.pk).update(is_default=False)
    currency.is_default = True
    currency.save(update_fields=["is_default", "updated_at"])
    return currency


@transaction.atomic
def update_currency(*, currency: Currency, code: str | None = None, name: str | None = None,
                    symbol: str | None = None) -> Currency:
    fields = []
    if code is not None:
        code = code.strip().upper()
        if Currency.objects.filter(company=currency.company, code=code).exclude(pk=currency.pk).exists():
            raise MasterDataError(f"'{code}' already exists for this company.")
        currency.code = code
        fields.append("code")
    if name is not None:
        currency.name = name.strip()
        fields.append("name")
    if symbol is not None:
        currency.symbol = symbol.strip()
        fields.append("symbol")
    if fields:
        currency.save(update_fields=fields + ["updated_at"])
    return currency


def delete_currency(*, currency: Currency) -> None:
    if currency.is_default:
        raise MasterDataError("Set a different currency as default before deleting this one.")
    count = _in_use_count(currency.company, field="currency", value=currency.code)
    if count:
        raise MasterDataError(f"{count} project(s) still use this currency.")
    currency.delete()


def create_project_type(*, company: Company, name: str) -> ProjectType:
    name = name.strip()
    if ProjectType.objects.filter(company=company, name=name).exists():
        raise MasterDataError(f"'{name}' already exists for this company.")
    return ProjectType.objects.create(
        company=company, name=name, sort_order=ProjectType.objects.filter(company=company).count(),
    )


def update_project_type(*, project_type: ProjectType, name: str) -> ProjectType:
    name = name.strip()
    if ProjectType.objects.filter(company=project_type.company, name=name).exclude(pk=project_type.pk).exists():
        raise MasterDataError(f"'{name}' already exists for this company.")
    project_type.name = name
    project_type.save(update_fields=["name", "updated_at"])
    return project_type


def delete_project_type(*, project_type: ProjectType) -> None:
    count = _in_use_count(project_type.company, field="project_type", value=project_type.name)
    if count:
        raise MasterDataError(f"{count} project(s) still use this type.")
    project_type.delete()


def create_project_priority(*, company: Company, name: str) -> ProjectPriority:
    name = name.strip()
    if ProjectPriority.objects.filter(company=company, name=name).exists():
        raise MasterDataError(f"'{name}' already exists for this company.")
    return ProjectPriority.objects.create(
        company=company, name=name, sort_order=ProjectPriority.objects.filter(company=company).count(),
    )


def update_project_priority(*, priority: ProjectPriority, name: str) -> ProjectPriority:
    name = name.strip()
    if ProjectPriority.objects.filter(company=priority.company, name=name).exclude(pk=priority.pk).exists():
        raise MasterDataError(f"'{name}' already exists for this company.")
    priority.name = name
    priority.save(update_fields=["name", "updated_at"])
    return priority


def delete_project_priority(*, priority: ProjectPriority) -> None:
    count = _in_use_count(priority.company, field="priority", value=priority.name)
    if count:
        raise MasterDataError(f"{count} project(s) still use this priority.")
    priority.delete()


def _party_in_use(instance) -> int:
    """How many of the company's projects still name this party, in any role."""
    from django.db.models import Q

    from apps.projects.models import Project

    q = Q()
    for field in _PARTY_PROJECT_FIELDS:
        q |= Q(**{field: instance.name})
    return Project.objects.filter(q, company=instance.company).count()


def create_party(*, company: Company, name: str, phone: str = "", email: str = "") -> Party:
    """Add one company to the roster. No role: a project decides what a party
    is to it by naming it in that role's field."""
    name = name.strip()
    if Party.objects.filter(company=company, name=name).exists():
        raise MasterDataError(f"'{name}' already exists for this company.")
    return Party.objects.create(
        company=company, name=name, phone=phone.strip(), email=email.strip(),
        sort_order=Party.objects.filter(company=company).count(),
    )


@transaction.atomic
def update_party(*, instance, name: str | None = None, phone: str | None = None, email: str | None = None):
    """Renaming carries the new name onto every project still using the old
    one, in every role. Without that a rename would orphan those projects —
    their stored string would no longer match anything in the list, so the
    dropdown would show them as blank even though nothing about the project
    changed."""
    fields = []
    if name is not None:
        name = name.strip()
        if model_has_name(Party, instance.company, name, exclude_pk=instance.pk):
            raise MasterDataError(f"'{name}' already exists for this company.")
        if name != instance.name:
            _rename_on_projects(instance, name)
        instance.name = name
        fields.append("name")
    if phone is not None:
        instance.phone = phone.strip()
        fields.append("phone")
    if email is not None:
        instance.email = email.strip()
        fields.append("email")
    if fields:
        instance.save(update_fields=fields + ["updated_at"])
    return instance


def model_has_name(model, company: Company, name: str, *, exclude_pk=None) -> bool:
    qs = model.objects.filter(company=company, name=name)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def _rename_on_projects(instance, new_name: str) -> None:
    from apps.projects.models import Project

    for field in _PARTY_PROJECT_FIELDS:
        (Project.objects.filter(company=instance.company, **{field: instance.name})
         .update(**{field: new_name}))


def delete_party(*, instance) -> None:
    count = _party_in_use(instance)
    if count:
        raise MasterDataError(f"{count} project(s) still use this entry.")
    instance.delete()
