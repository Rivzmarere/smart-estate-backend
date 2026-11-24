"""
Levy account balances.

Payments are not tied to one invoice: money received pays off the oldest
invoice first. "Arrears" is what is still owed on invoices past their due date.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from home.models import Home

from .models import ExchangeRate, Invoice, Payment, money

ZERO = Decimal("0.00")


def allocate(invoices, paid_total, today):
    """Spread `paid_total` over invoices oldest-first. Returns (rows, arrears, credit)."""
    remaining = paid_total
    rows, arrears = [], ZERO
    for invoice in sorted(invoices, key=lambda i: (i.due_date, i.id)):
        applied = min(invoice.amount_usd, max(remaining, ZERO))
        remaining -= applied
        outstanding = invoice.amount_usd - applied
        if outstanding <= 0:
            state = "paid"
        elif invoice.due_date < today:
            state = "overdue"
            arrears += outstanding
        elif applied > 0:
            state = "part paid"
        else:
            state = "open"
        rows.append({"invoice": invoice, "paid": money(applied), "outstanding": money(outstanding), "state": state})
    return rows, money(arrears), money(max(remaining, ZERO))


def account(home, today=None, lease=None):
    """
    Full account for one home. A rented property's account is its current
    tenant's (their lease), so one tenant never sees or owes another's rent.
    """
    today = today or timezone.localdate()
    if lease is None:
        from rentals.models import Lease

        lease = Lease.objects.filter(home=home, status=Lease.ACTIVE).first()
    scope = {"lease": lease} if lease else {"home": home}
    invoices = list(Invoice.objects.filter(void=False, **scope))
    paid = Payment.objects.filter(status=Payment.PAID, **scope).aggregate(total=Sum("amount_usd"))["total"] or ZERO
    invoiced = sum((i.amount_usd for i in invoices), ZERO)
    rows, arrears, credit = allocate(invoices, paid, today)
    return {
        "home": home,
        "lease": lease,
        "invoiced": money(invoiced),
        "paid": money(paid),
        "balance": money(invoiced - paid),
        "arrears": arrears,
        "credit": credit,
        "invoices": rows,
    }


def all_accounts(today=None):
    """One summary row per active home, cheaply (two queries plus homes)."""
    today = today or timezone.localdate()
    by_home = defaultdict(list)
    for invoice in Invoice.objects.filter(void=False).only("id", "home_id", "amount_usd", "due_date"):
        by_home[invoice.home_id].append(invoice)
    paid = dict(
        Payment.objects.filter(status=Payment.PAID).values_list("home_id").annotate(total=Sum("amount_usd")).values_list("home_id", "total")
    )
    last_paid = {}
    for home_id, when in Payment.objects.filter(status=Payment.PAID).exclude(method__in=Payment.NOT_RECEIVED).order_by("home_id", "-paid_at").values_list("home_id", "paid_at"):
        last_paid.setdefault(home_id, when)

    rows = []
    for home in Home.objects.filter(status=True).select_related("stand", "resident").order_by("stand__stand_number", "id"):
        invoices = by_home.get(home.id, [])
        home_paid = paid.get(home.id) or ZERO
        invoiced = sum((i.amount_usd for i in invoices), ZERO)
        allocated, arrears, _ = allocate(invoices, home_paid, today)
        oldest_overdue = next((r["invoice"].due_date for r in allocated if r["state"] == "overdue"), None)
        rows.append({
            "home_id": home.id,
            "stand_number": home.stand.stand_number,
            "address": home.address,
            "resident": f"{home.resident.name} {home.resident.surname}" if home.resident else "",
            "resident_phone": (home.resident.phone_number1 or "") if home.resident else "",
            "invoiced": money(invoiced),
            "paid": money(home_paid),
            "balance": money(invoiced - home_paid),
            "arrears": arrears,
            "oldest_overdue": oldest_overdue,
            "last_paid_at": last_paid.get(home.id),
        })
    return rows


def in_zig(amount_usd, day=None):
    """(ZiG amount, rate) at the rate for `day`, or (None, None) if no rate is set."""
    rate = ExchangeRate.on(day)
    if rate is None:
        return None, None
    return money(amount_usd * rate.zig_per_usd), rate.zig_per_usd


def to_usd(amount, currency, rate):
    if currency == Payment.USD:
        return money(amount)
    return money(Decimal(amount) / Decimal(rate))


def fmt_usd(value):
    return f"USD {money(value):,.2f}"


def fmt_zig(value):
    return f"ZiG {money(value):,.2f}"
