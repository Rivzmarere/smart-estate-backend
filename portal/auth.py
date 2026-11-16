"""
Signing residents in to the portal with a one-time code sent by SMS.

Residents are not staff Users. A signed-in resident is a ResidentPrincipal
carrying their phone number and estate; the token is accepted only by the
portal's own endpoints (header  Authorization: Resident <token>), so it can
never open a staff endpoint.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.permissions import BasePermission

from estates.models import Estate
from sms.sender import send_sms, zimbabwe_mobile
from whatsapp.notifications import notify

from .models import LoginCode

TOKEN_SALT = "smart-estate.portal.resident"
TOKEN_AGE = timedelta(days=30)
CODE_LIFETIME = timedelta(minutes=10)
MAX_CODES_PER_WINDOW = 3
CODE_WINDOW = timedelta(minutes=15)


class ResidentPrincipal:
    """request.user for a resident signed in to the portal."""

    is_authenticated = True
    is_anonymous = False
    is_superuser = False
    is_staff = False
    is_active = True
    role = "Resident"

    def __init__(self, phone, estate):
        self.phone = phone
        self.estate = estate
        self.estate_id = estate.pk
        # Unique per resident, so rate limits are per person.
        self.pk = self.id = f"resident:{phone}"

    def __str__(self):
        return self.phone


def _hash(phone, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_code(estate, phone):
    """Send a 6-digit code. Returns False if too many were asked for recently."""
    recent = LoginCode.objects.filter(estate=estate, phone=phone, created_at__gte=timezone.now() - CODE_WINDOW).count()
    if recent >= MAX_CODES_PER_WINDOW:
        return False
    code = f"{secrets.randbelow(1_000_000):06d}"
    LoginCode.objects.filter(estate=estate, phone=phone, used=False).update(used=True)  # only the newest works
    LoginCode.objects.create(estate=estate, phone=phone, code_hash=_hash(phone, code), expires_at=timezone.now() + CODE_LIFETIME)
    text = f"Your {estate.name} portal code is {code}. It expires in 10 minutes. Never share it."
    if not notify(phone, text):  # WhatsApp is free when the resident has written recently
        send_sms(phone, text)
    return True


def check_code(estate, phone, code):
    """True and the code is used up, if it is right."""
    login = LoginCode.objects.filter(estate=estate, phone=phone, used=False).first()
    if login is None or not login.usable:
        return False
    if not hmac.compare_digest(login.code_hash, _hash(phone, str(code).strip())):
        login.attempts += 1
        login.save(update_fields=["attempts"])
        return False
    login.used = True
    login.save(update_fields=["used"])
    return True


def make_token(estate, phone):
    return signing.dumps({"p": phone, "e": estate.pk}, salt=TOKEN_SALT, compress=True)


def read_token(token):
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_AGE)
    except signing.BadSignature:
        return None
    estate = Estate.objects.filter(pk=data.get("e"), active=True).first()
    phone = zimbabwe_mobile(data.get("p"))
    return ResidentPrincipal(phone, estate) if estate and phone else None


class ResidentAuthentication(BaseAuthentication):
    keyword = "Resident"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].decode().lower() != self.keyword.lower():
            return None
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Malformed sign-in token.")
        principal = read_token(parts[1].decode())
        if principal is None:
            raise exceptions.AuthenticationFailed("Your sign-in has expired. Please sign in again.")
        return principal, None

    def authenticate_header(self, request):
        return self.keyword


class IsResident(BasePermission):
    message = "Please sign in to the residents' portal."

    def has_permission(self, request, view):
        return isinstance(request.user, ResidentPrincipal)
