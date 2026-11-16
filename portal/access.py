"""
Which homes a phone number may act for, and what it may do there.
Used by the portal, USSD, the WhatsApp bot and the public booking form.
"""

from dataclasses import dataclass, field

from django.db.models import Q

from home.models import Home
from visit.utilities import phone_variants

OWNER = "owner"
RESIDENT = "resident"
MEMBER = "member"
MEMBER_LIMITED = "member_limited"  # a household member who may not book visitors

# What each way of belonging to a home allows.
PERMISSIONS = {
    "visitors": {OWNER, RESIDENT, MEMBER},
    "repairs": {OWNER, RESIDENT, MEMBER, MEMBER_LIMITED},
    "emergency": {OWNER, RESIDENT, MEMBER, MEMBER_LIMITED},
    "chat": {OWNER, RESIDENT, MEMBER, MEMBER_LIMITED},
    "levy": {OWNER, RESIDENT},
    "household": {OWNER, RESIDENT},  # add or remove family / workers
    "tenancy": {OWNER},  # change who the main resident is
}

PHONE_FIELDS = ("phone_number1", "phone_number2", "phone_number3", "phone_number4")


@dataclass
class HomeAccess:
    home: Home
    roles: set = field(default_factory=set)

    def can(self, action):
        if not self.home.estate.offers(action):  # e.g. no gate or security team in a rental portfolio
            return False
        return bool(self.roles & PERMISSIONS[action])

    @property
    def label(self):
        for role in (RESIDENT, OWNER, MEMBER, MEMBER_LIMITED):
            if role in self.roles:
                return role
        return ""


def _match(prefix, fields, variants):
    query = Q()
    for f in fields:
        query |= Q(**{f"{prefix}{f}__in": variants})
    return query


def homes_for_phone(phone, across_estates=False, action=None):
    """
    [HomeAccess] for every active home this number belongs to, best first.
    across_estates: look in every estate (WhatsApp and USSD use one number for all).
    action: keep only homes where the number may do this (see PERMISSIONS).
    """
    variants = phone_variants(phone)
    if not variants:
        return []
    from estates.context import explicit_estate

    if across_estates:
        working_in = explicit_estate()
        homes = Home.all_estates.all()
        if working_in is not None and getattr(working_in, "sandbox", False):
            homes = homes.filter(estate=working_in)  # a simulator works inside its own sandbox estate
        else:
            homes = homes.filter(estate__sandbox=False)  # real numbers never land in a demo estate
    else:
        homes = Home.objects.all()
    homes = homes.filter(status=True, estate__active=True).select_related("stand", "resident", "owner", "estate")

    found = {}

    def add(qs, role):
        for home in qs:
            found.setdefault(home.pk, HomeAccess(home)).roles.add(role)

    add(homes.filter(_match("resident__", PHONE_FIELDS, variants), resident__status=True), RESIDENT)
    add(homes.filter(_match("owner__", ("phone_number1", "phone_number2"), variants)), OWNER)
    add(homes.filter(members__phone__in=variants, members__active=True, members__can_book_visitors=True).distinct(), MEMBER)
    add(homes.filter(members__phone__in=variants, members__active=True, members__can_book_visitors=False).distinct(), MEMBER_LIMITED)

    result = list(found.values())
    if action:
        result = [a for a in result if a.can(action)]
    order = {RESIDENT: 0, MEMBER: 1, OWNER: 2, MEMBER_LIMITED: 3}
    result.sort(key=lambda a: (order.get(a.label, 9), a.home.pk))
    return result


def access_to(home, phone):
    """The HomeAccess for one home, or None."""
    for access in homes_for_phone(phone, across_estates=True):
        if access.home.pk == home.pk:
            return access
    return None
