"""
Helpers shared by visitor bookings, whitelist guests and complaints.
"""

import re
import secrets

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


def search_auth(stand, phone_number, action="visitors"):
    """
    True only if this phone number belongs to a home on this stand (as its
    resident, a household member or its owner) and may do this there.
    """
    from portal.access import homes_for_phone

    return any(a.home.stand.stand_number == int(stand) for a in homes_for_phone(phone_number, action=action))


def search_home(stand):
    """Return the home on this stand as a dict with at least an ``address`` key."""
    home = Home.objects.filter(stand__stand_number=stand, status=True).first()
    return {"address": home.address if home else ""}
