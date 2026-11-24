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
from rest_framework.exceptions import APIException

from . import context


class Organisation(models.Model):
    """
    A customer account that runs several estates or rental portfolios:
    a managing agent, or a landlord with many properties.
    Its staff (User.organisation) work across all of its estates.
    """

    AGENT = "agent"
    LANDLORD = "landlord"
    KINDS = [(AGENT, "Managing agent"), (LANDLORD, "Landlord")]

    name = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=10, choices=KINDS, default=AGENT)
    active = models.BooleanField(default=True)
    contact_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    price_per_unit_usd = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, help_text="What this customer pays per home or property per month"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Estate(models.Model):
    GATED = "estate"
    RENTAL = "rental"
    KINDS = [(GATED, "Gated estate or complex"), (RENTAL, "Rental portfolio")]
    # What residents of a rental portfolio cannot use: there is no gate and no security team.
    GATED_ONLY = {"visitors", "emergency", "tenancy"}  # tenancy: leases are kept by the landlord

    name = models.CharField(max_length=120)
    organisation = models.ForeignKey(
        Organisation, on_delete=models.PROTECT, null=True, blank=True, related_name="estates",
        help_text="The managing agent or landlord this belongs to. Empty for an estate that runs itself.",
    )
    kind = models.CharField(max_length=10, choices=KINDS, default=GATED)
    management_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text="Rental portfolios: the agent's share of rent collected, shown on owner statements"
    )
    rent_reminders = models.BooleanField(default=True, help_text="Rental portfolios: remind tenants before rent is due and when it is late")
    slug = models.SlugField(max_length=60, unique=True, help_text="Short name used in the resident portal address")
    active = models.BooleanField(default=True)
    sandbox = models.BooleanField(
        default=False, help_text="Demo estate for testers: SMS/WhatsApp are captured, not sent; payments are simulated"
    )
    address = models.CharField(max_length=200, blank=True)
    # Who residents and the system reach
    office_phone = models.CharField(max_length=20, blank=True, help_text="Shown to residents. A mobile number also gets an SMS when a resident asks to chat.")
    office_hours = models.CharField(max_length=120, blank=True, help_text="e.g. Mon-Fri 08:00-16:30")
    emergency_phones = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated mobile numbers SMSed when a resident raises an emergency (security control room, manager)"
    )
    # Residents' portal
    household_approval = models.BooleanField(
        default=True, help_text="Household changes from the portal (new tenant, new member) wait for the office to approve"
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
    def is_rental(self):
        return self.kind == self.RENTAL

    @property
    def bill_word(self):
        """What residents pay here: a levy in an estate, rent in a rental portfolio."""
        return "rent" if self.is_rental else "levy"

    def offers(self, feature):
        return not (self.is_rental and feature in self.GATED_ONLY)

    @property
    def emergency_numbers(self):
        return [n.strip() for n in self.emergency_phones.split(",") if n.strip()]

    def __str__(self):
        return self.name


class NoEstateChosen(ValueError, APIException):
    """Saving estate data with no estate selected. In a request this is answered with 400, not a crash."""

    status_code = 400
    default_detail = "Choose an estate first."

    def __init__(self, reason=""):
        ValueError.__init__(self, reason)
        APIException.__init__(self)


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
                raise NoEstateChosen(f"Cannot save {type(self).__name__} without an estate")
            self.estate = estate
        super().save(*args, **kwargs)


class SandboxMessage(EstateScoped):
    """An SMS or WhatsApp message a sandbox estate would have sent. Nothing leaves the server."""

    SMS = "sms"
    WHATSAPP = "whatsapp"
    CHANNELS = [(SMS, "SMS"), (WHATSAPP, "WhatsApp")]

    channel = models.CharField(max_length=10, choices=CHANNELS)
    to = models.CharField(max_length=32, db_index=True)
    text = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
