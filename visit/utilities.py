"""
Helpers shared by visitor bookings, whitelist guests and complaints.
"""

import re
import secrets

from django.db.models import Q

from home.models import Home

# No 0/O or 1/I, so codes are easy to read out at the gate.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def random_numbers(length=CODE_LENGTH):
    """Return a random, human-friendly access code."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def phone_variants(phone_number):
    """
    Zimbabwean numbers are written as 0771234567, +263771234567 or 263771234567.
    Return every spelling so a match works whichever one was stored.
    """
    raw = str(phone_number or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return set()
    if digits.startswith("263"):
        local = digits[3:]
    elif digits.startswith("0"):
        local = digits[1:]
    else:
        local = digits
    return {raw, digits, "0" + local, "263" + local, "+263" + local}


def _resident_phone_query(phone_number):
    variants = phone_variants(phone_number)
    query = Q()
    for field in ("phone_number1", "phone_number2", "phone_number3", "phone_number4"):
        query |= Q(**{f"resident__{field}__in": variants})
    return query


def search_auth(stand, phone_number):
    """
    True only if the phone number belongs to the resident of a home on this stand.
    (Previously any resident's number unlocked every stand.)
    """
    if not phone_variants(phone_number):
        return False
    return (
        Home.objects.filter(stand__stand_number=stand, status=True, resident__isnull=False)
        .filter(_resident_phone_query(phone_number))
        .exists()
    )


def search_home(stand):
    """Return the home on this stand as a dict with at least an ``address`` key."""
    home = Home.objects.filter(stand__stand_number=stand, status=True).first()
    return {"address": home.address if home else ""}
