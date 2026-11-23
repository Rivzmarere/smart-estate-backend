"""
audit.record(): write one line of history.

    from audit.log import record
    record("payment.recorded", "Recorded USD 50.00 cash for 12 Acacia Drive", payment, area="money", amount="50.00")

The user and estate come from the current request unless given. Failing to
write history never breaks the action itself.
"""

import json
import logging

from django.core.serializers.json import DjangoJSONEncoder

from estates.context import ALL, current_estate, current_user

log = logging.getLogger(__name__)


def _name(user):
    if user is None:
        return "System"
    return (user.get_full_name() or user.username)[:120]


def record(action, summary, obj=None, area="data", user=None, estate=None, **details):
    from .models import AuditEntry

    try:
        user = user or current_user()
        if estate is None:
            estate = getattr(obj, "estate", None) if obj is not None and getattr(obj, "estate_id", None) else current_estate()
        if estate is ALL:
            estate = None
        clean = json.loads(json.dumps(details, cls=DjangoJSONEncoder)) if details else {}
        return AuditEntry.objects.create(
            estate=estate, user=user, who=_name(user), area=area, action=action, summary=summary[:300],
            object_type=obj._meta.model_name if obj is not None else "", object_id=str(obj.pk) if obj is not None else "",
            details=clean,
        )
    except Exception:  # history must never stop the real work
        log.exception("Could not record %s", action)
        return None


def name_of(person):
    return f"{person.name} {person.surname}".strip() if person is not None else ""


def usd(value):
    return f"USD {value:,.2f}"
