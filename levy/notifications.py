"""Receipts and payment messages to residents: WhatsApp first, SMS otherwise."""

import logging

from django.conf import settings
from django.utils import timezone

from sms.sender import send_sms
from whatsapp.notifications import notify

from .accounts import account, fmt_usd, fmt_zig
from .models import Payment

logger = logging.getLogger(__name__)


def amount_text(payment):
    if payment.currency == Payment.ZWG:
        return f"{fmt_zig(payment.amount)} ({fmt_usd(payment.amount_usd)})"
    return fmt_usd(payment.amount)


def receipt_text(payment, balance):
    when = timezone.localtime(payment.paid_at).strftime("%d %b %Y %H:%M")
    lines = [
        f"🧾 *Smart Estate receipt {payment.receipt_number}*",
        f"Received: {amount_text(payment)}",
        f"For: {payment.home.address} (stand {payment.home.stand.stand_number})",
        f"Paid by: {payment.get_method_display()}" + (f", ref {payment.paynow_reference or payment.reference}" if (payment.paynow_reference or payment.reference) else ""),
        f"Date: {when}",
    ]
    if balance > 0:
        lines.append(f"Balance still owing: {fmt_usd(balance)}")
    elif balance < 0:
        lines.append(f"Credit on your account: {fmt_usd(-balance)}")
    else:
        lines.append(f"Your {payment.home.estate.bill_word} account is fully paid. Thank you!")
    return "\n".join(lines)


def send_receipt(payment):
    """Send the receipt to whoever paid (WhatsApp) or the resident (SMS). Never raises."""
    try:
        balance = account(payment.home, lease=payment.lease)["balance"]
        phone = payment.wa_id or payment.phone or (payment.home.resident.phone_number1 if payment.home.resident else "")
        if not phone:
            return False
        text = receipt_text(payment, balance)
        if notify(
            phone,
            text,
            settings.WHATSAPP_TEMPLATE_PAYMENT_RECEIPT,
            [payment.receipt_number, amount_text(payment), payment.home.address, fmt_usd(balance)],
        ):
            return True
        return send_sms(
            phone,
            f"Smart Estate receipt {payment.receipt_number}: {amount_text(payment)} received for "
            f"{payment.home.address}. Balance {fmt_usd(balance)}.",
        )
    except Exception:
        logger.exception("Could not send receipt for payment %s", payment.pk)
        return False


def send_payment_failed(payment):
    if not payment.wa_id:
        return False
    reason = "you cancelled it" if payment.status == Payment.CANCELLED else "it did not go through"
    return notify(
        payment.wa_id,
        f"Your {payment.home.estate.bill_word} payment of {amount_text(payment)} was not completed ({reason}). "
        "Nothing was taken from your wallet. Type *menu* to try again.",
    )
