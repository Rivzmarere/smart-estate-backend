"""
Estates: one installation serves many estates.

Every estate-owned record (stands, homes, residents, visits, levies, ...)
inherits EstateScoped. Its default manager only returns rows of the
*current estate*, worked out once per request (see estates.context), so a
query written anywhere in the code base cannot see another estate's data.
New rows are stamped with the current estate when they are saved.

Reference lists (genders, statuses, categories, transport types) are shared.
"""

from django.db import models
from django.utils.text import slugify

from . import context


class Estate(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=60, unique=True, help_text="Short name used in the resident portal address")
    active = models.BooleanField(default=True)
    address = models.CharField(max_length=200, blank=True)
    # Who residents and the system reach
    office_phone = models.CharField(max_length=20, blank=True, help_text="Shown to residents; office hand-off alerts go here")
    office_hours = models.CharField(max_length=120, blank=True, help_text="e.g. Mon-Fri 08:00-16:30")
    emergency_phones = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated numbers SMSed when a resident raises an emergency (security control room, manager)"
    )
    # Paynow (blank = use the server-wide settings)
    paynow_usd_integration_id = models.CharField(max_length=20, blank=True)
    paynow_usd_integration_key = models.CharField(max_length=80, blank=True)
    paynow_zwg_integration_id = models.CharField(max_length=20, blank=True)
    paynow_zwg_integration_key = models.CharField(max_length=80, blank=True)
    paynow_auth_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:60] or "estate"
        super().save(*args, **kwargs)

    @property
    def emergency_numbers(self):
        return [n.strip() for n in self.emergency_phones.split(",") if n.strip()]

    def __str__(self):
        return self.name


class EstateScopedManager(models.Manager):
    """Only the current estate's rows (all rows for platform staff working across estates)."""

    def get_queryset(self):
        qs = super().get_queryset()
        estate = context.current_estate()
        if estate is context.ALL:
            return qs
        if estate is None:
            return qs.none()
        return qs.filter(estate=estate)


class EstateScoped(models.Model):
    # Not editable: never taken from client input, always the current estate.
    estate = models.ForeignKey(Estate, on_delete=models.PROTECT, related_name="+", editable=False)

    objects = EstateScopedManager()
    all_estates = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.estate_id:
            estate = context.current_estate()
            if estate is None or estate is context.ALL:
                raise ValueError(f"Cannot save {type(self).__name__} without an estate")
            self.estate = estate
        super().save(*args, **kwargs)
