"""
Paged lists for the back office tables (homes, owners, residents, ...).

The tables send ?page=, ?search= and a status filter. Empty filters arrive as
"", "undefined" or "null" depending on the form, so those all mean "no filter".
"""

import math

from django.db.models import Q
from rest_framework.response import Response

EMPTY = {"", "undefined", "null", "none", "all"}
PER_PAGE = 20
MAX_PER_PAGE = 100


def param(request, *names):
    """The first of these query parameters that has a real value, else ""."""
    for name in names:
        value = (request.GET.get(name) or "").strip()
        if value.lower() not in EMPTY:
            return value
    return ""


def number(value):
    return int(value) if str(value).isdigit() else None


def flag(value):
    """'true' / 'false' (any case, or 1 / 0, active / inactive) -> True / False; anything else -> None."""
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "active"):
        return True
    if text in ("false", "0", "no", "inactive"):
        return False
    return None


def search(queryset, text, fields):
    """Rows where every word appears in one of the fields (so "rudo moyo" finds Rudo Moyo)."""
    for word in text.split()[:5]:
        condition = Q()
        for field in fields:
            condition |= Q(**{f"{field}__icontains": word})
        queryset = queryset.filter(condition)
    return queryset


def page(request, queryset, serializer, per_page=PER_PAGE, **serializer_kwargs):
    try:
        number_ = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        number_ = 1
    try:
        size = min(MAX_PER_PAGE, max(5, int(request.GET.get("per_page", per_page))))
    except (TypeError, ValueError):
        size = per_page
    total = queryset.count()
    start = (number_ - 1) * size
    rows = serializer(queryset[start:start + size], many=True, **serializer_kwargs).data
    return Response({"data": rows, "total": total, "page": number_, "per_page": size, "last_page": max(1, math.ceil(total / size))})
