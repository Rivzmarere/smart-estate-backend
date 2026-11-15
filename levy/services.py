"""Starting a mobile-money levy payment (used by the WhatsApp bot)."""

from datetime import timedelta

from django.utils import timezone

from . import paynow
from .accounts import in_zig, money
from .models import Payment

# A resident can only have one payment prompt waiting at a time.
PENDING_WINDOW = timedelta(minutes=5)


def pending_payment(home):
    return Payment.objects.filter(
        home=home, status=Payment.PENDING, created_at__gte=timezone.now() - PENDING_WINDOW
    ).first()


def start_payment(home, amount_usd, currency, phone, wa_id=""):
    """
    Create a pending payment and send the PIN prompt to `phone`.
    Returns (payment, instructions). Raises paynow.PaynowError.
    """
    method = paynow.method_for_phone(phone)
    if method is None:
        raise paynow.PaynowError("Use an EcoCash or OneMoney number.")
    amount_usd = money(amount_usd)
    if currency == Payment.ZWG:
        amount, rate = in_zig(amount_usd)
        if amount is None:
            raise paynow.PaynowError("ZiG payments are not available today.")
    else:
        amount, rate = amount_usd, None
    payment = Payment.objects.create(
        home=home, currency=currency, amount=amount, exchange_rate=rate, amount_usd=amount_usd, method=method,
        status=Payment.PENDING, channel=Payment.WHATSAPP, phone=phone, wa_id=wa_id,
    )
    try:
        instructions = paynow.start_mobile_payment(payment, f"Levy {home.address}")
    except paynow.PaynowError as exc:
        payment.status = Payment.FAILED
        payment.failure_reason = str(exc)[:300]
        payment.save(update_fields=["status", "failure_reason"])
        raise
    return payment, instructions
