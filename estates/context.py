"""
Which estate the current code is working for.

Resolved, in order:
  1. an explicit `use_estate(...)` block (WhatsApp bot, Paynow callbacks, commands);
  2. the logged-in user's estate (platform superusers may pick one with the
     X-Estate header, and otherwise see every estate; staff of a managing
     agent or landlord pick one of *their* estates the same way);
  3. for the public resident portal: the X-Estate header or ?estate= slug;
  4. when the installation has exactly one active estate: that one.

If none applies the answer is None, and estate-scoped queries return nothing.
"""

import contextvars
from contextlib import contextmanager

ALL = object()  # sentinel: no filtering (platform staff)

_override = contextvars.ContextVar("estate_override", default=None)
_request = contextvars.ContextVar("estate_request", default=None)

HEADER = "HTTP_X_ESTATE"


@contextmanager
def use_estate(estate):
    token = _override.set(estate)
    try:
        yield estate
    finally:
        _override.reset(token)


def set_request(request):
    return _request.set(request)


def reset_request(token):
    _request.reset(token)


def _by_slug(slug):
    from .models import Estate

    return Estate.objects.filter(slug=slug, active=True).first() if slug else None


def _only_estate():
    from .models import Estate

    estates = list(Estate.objects.filter(active=True)[:2])
    return estates[0] if len(estates) == 1 else None


def _organisation_estate(user, slug):
    """One of the organisation's own estates: the one asked for, or its only one. Never another customer's."""
    from .models import Estate

    if not user.organisation.active:
        return None
    estates = Estate.objects.filter(organisation_id=user.organisation_id, active=True)
    if slug:
        return estates.filter(slug=slug).first()
    estates = list(estates[:2])
    return estates[0] if len(estates) == 1 else None


def _resolve(request):
    user = getattr(request, "user", None)
    requested = request.META.get(HEADER) or request.GET.get("estate")
    if user is not None and user.is_authenticated:
        if getattr(user, "estate_id", None):
            estate = user.estate
            owner = estate.organisation if estate.organisation_id else None
            return estate if estate.active and (owner is None or owner.active) else None  # switched off: no data
        if user.is_superuser:
            return _by_slug(requested) if requested else ALL
        if getattr(user, "organisation_id", None):
            return _organisation_estate(user, requested)
        return _only_estate()
    if requested:
        return _by_slug(requested)
    return _only_estate()


def current_estate():
    override = _override.get()
    if override is not None:
        return override
    request = _request.get()
    if request is None:
        return _only_estate()
    user = getattr(request, "user", None)
    key = (getattr(user, "pk", None), getattr(user, "is_authenticated", False))
    cached = getattr(request, "_estate_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    estate = _resolve(request)
    request._estate_cache = (key, estate)
    return estate


class EstateMiddleware:
    """Makes the request available to current_estate() for the duration of the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_request(request)
        try:
            return self.get_response(request)
        finally:
            reset_request(token)


def current_user():
    """The logged-in user of the current request, or None."""
    request = _request.get()
    user = getattr(request, "user", None) if request is not None else None
    # Staff accounts only: a resident signed in to the portal is not a User.
    if user is None or not user.is_authenticated or not hasattr(user, "_meta"):
        return None
    return user


def explicit_estate():
    """The estate set with use_estate(), if any (simulators and background jobs)."""
    return _override.get()


def in_sandbox():
    """True while working for a sandbox estate: nothing may be sent for real."""
    estate = current_estate()
    return estate is not None and estate is not ALL and getattr(estate, "sandbox", False)
