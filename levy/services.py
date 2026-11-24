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
        instructions = paynow.start_mobile_payment(payment, f"{home.estate.bill_word.capitalize()} {home.address}")
    except paynow.PaynowError as exc:
        payment.status = Payment.FAILED
        payment.failure_reason = str(exc)[:300]
        payment.save(update_fields=["status", "failure_reason"])
        raise
    return payment, instructions


def refresh_payment(payment, give_up_after=None):
    """
    Ask Paynow (or the sandbox) about a waiting payment and act on the answer:
    receipt when paid, a message when it failed. Returns the payment's status.
    """
    from django.db import transaction

    from .notifications import send_payment_failed, send_receipt

    with transaction.atomic():
        locked = Payment.objects.select_for_update().select_related("estate", "home__stand", "home__resident").get(pk=payment.pk)
        if locked.status != Payment.PENDING:
            return locked.status
        status = paynow.poll(locked)
        if status == Payment.PENDING and give_up_after and locked.created_at < timezone.now() - give_up_after:
            locked.status = Payment.FAILED
            locked.failure_reason = "No answer from Paynow within 24 hours"
            locked.save(update_fields=["status", "failure_reason"])
            status = Payment.FAILED
    if status == Payment.PAID:
        send_receipt(locked)
    elif status in (Payment.FAILED, Payment.CANCELLED):
        send_payment_failed(locked)
    return status
