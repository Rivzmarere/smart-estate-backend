"""
Paynow Zimbabwe: mobile-money payments (EcoCash, OneMoney, InnBucks).

Flow ("express checkout"):
  1. We POST the payment to Paynow with the payer's phone number.
  2. Paynow pushes a USSD prompt to the phone; the payer enters their PIN.
  3. Paynow POSTs the result to our result URL, and we can also poll for it.

Every message both ways is signed: SHA-512 over the field values in the
order sent, followed by the integration key, upper-case hex.

Each Paynow integration handles one currency, so USD and ZiG have separate
integration IDs and keys (settings.PAYNOW_USD_* and PAYNOW_ZWG_*).

With PAYNOW_DRY_RUN (default in development and tests) nothing leaves the
server: requests are recorded in OUTBOX and the result is reported later
through the result endpoint, as Paynow would.
"""

import hashlib
import hmac
import logging
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode

from django.conf import settings

from .models import Payment

logger = logging.getLogger(__name__)

REMOTE_TRANSACTION_URL = "https://www.paynow.co.zw/interface/remotetransaction"

OUTBOX = []  # dry-run requests, newest last

PAID_STATUSES = {"paid", "awaiting delivery", "delivered"}
FAILED_STATUSES = {"failed", "disputed", "refunded"}
CANCELLED_STATUSES = {"cancelled"}

# Which mobile-money service a Zimbabwean number belongs to.
METHOD_BY_PREFIX = {"77": Payment.ECOCASH, "78": Payment.ECOCASH, "71": Payment.ONEMONEY}


class PaynowError(Exception):
    pass


def integration(currency, estate=None):
    """
    (id, key) for a currency, or (None, None) if it is not configured.
    Each estate can have its own Paynow account (money goes to that estate);
    otherwise the server-wide settings are used.
    """
    if currency == Payment.ZWG:
        own = (estate.paynow_zwg_integration_id, estate.paynow_zwg_integration_key) if estate else ("", "")
        server = settings.PAYNOW_ZWG_INTEGRATION_ID, settings.PAYNOW_ZWG_INTEGRATION_KEY
    else:
        own = (estate.paynow_usd_integration_id, estate.paynow_usd_integration_key) if estate else ("", "")
        server = settings.PAYNOW_USD_INTEGRATION_ID, settings.PAYNOW_USD_INTEGRATION_KEY
    for pair in (own, server):
        if all(pair):
            return pair
    return None, None


def auth_email(estate=None):
    return (estate.paynow_auth_email if estate else "") or settings.PAYNOW_AUTH_EMAIL


def available_currencies(estate=None):
    return [c for c in (Payment.USD, Payment.ZWG) if integration(c, estate)[0]]


def method_for_phone(local_number):
    """0772111111 -> 'ecocash'; None if the network is not supported."""
    digits = "".join(ch for ch in str(local_number) if ch.isdigit())
    if digits.startswith("263"):
        digits = "0" + digits[3:]
    return METHOD_BY_PREFIX.get(digits[1:3]) if len(digits) == 10 and digits.startswith("0") else None


def sign(pairs, key):
    text = "".join(str(value) for name, value in pairs if name.lower() != "hash") + key
    return hashlib.sha512(text.encode("utf-8")).hexdigest().upper()


def verify(pairs, key):
    received = next((value for name, value in pairs if name.lower() == "hash"), "")
    return bool(received) and hmac.compare_digest(received.upper(), sign(pairs, key))


def _post(url, pairs):
    request = urllib.request.Request(
        url,
        data=urlencode(pairs).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return parse_qsl(response.read().decode(), keep_blank_values=True)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PaynowError(f"Could not reach Paynow: {exc}") from exc


def start_mobile_payment(payment, description):
    """
    Ask Paynow to send the payment prompt to payment.phone.
    Saves poll_url / paynow_status on the payment; returns Paynow's instructions text.
    Raises PaynowError if Paynow refuses.
    """
    integration_id, key = integration(payment.currency, payment.estate)
    if not integration_id:
        raise PaynowError(f"Paynow is not set up for {payment.currency}.")
    pairs = [
        ("id", integration_id),
        ("reference", payment.reference_for_paynow),
        ("amount", f"{payment.amount:.2f}"),
        ("additionalinfo", description[:100]),
        ("returnurl", settings.RESIDENT_PORTAL_URL),
        ("resulturl", f"{settings.PUBLIC_API_URL}/paynow/result/{payment.pk}"),
        ("authemail", auth_email(payment.estate)),
        ("phone", payment.phone),
        ("method", payment.method),
        ("status", "Message"),
    ]
    pairs.append(("hash", sign(pairs, key)))

    if settings.PAYNOW_DRY_RUN:
        OUTBOX.append(dict(pairs))
        reply = [("status", "Ok"), ("pollurl", f"https://www.paynow.co.zw/Interface/CheckPayment/?guid=dry-run-{payment.pk}"),
                 ("instructions", "Dial *151*2*4# if no prompt appears"), ("paynowreference", f"DRY{payment.pk}")]
        reply.append(("hash", sign(reply, key)))
    else:
        reply = _post(REMOTE_TRANSACTION_URL, pairs)

    fields = dict(reply)
    if fields.get("status", "").lower() != "ok":
        raise PaynowError(fields.get("error") or "Paynow did not accept the payment.")
    if not verify(reply, key):
        raise PaynowError("Paynow's reply failed the signature check.")
    payment.poll_url = fields.get("pollurl", "")
    payment.paynow_reference = fields.get("paynowreference", "")
    payment.paynow_status = "Sent"
    payment.save(update_fields=["poll_url", "paynow_reference", "paynow_status"])
    return fields.get("instructions", "")


def apply_status(payment, pairs):
    """
    Apply a signed status message (from the result URL or a poll) to the payment.
    Returns "paid" the first time the payment is confirmed, otherwise the payment's status.
    """
    _, key = integration(payment.currency, payment.estate)
    if not key or not verify(pairs, key):
        raise PaynowError("Bad Paynow signature")
    fields = {name.lower(): value for name, value in pairs}
    if fields.get("reference") and fields["reference"] != payment.reference_for_paynow:
        raise PaynowError("Reference does not match this payment")
    status = (fields.get("status") or "").strip()
    payment.paynow_status = status[:40]
    payment.paynow_reference = fields.get("paynowreference", payment.paynow_reference)[:40]

    if payment.status != Payment.PENDING:
        payment.save(update_fields=["paynow_status", "paynow_reference"])
        return payment.status

    lowered = status.lower()
    if lowered in PAID_STATUSES:
        try:
            amount_ok = abs(float(fields.get("amount", payment.amount)) - float(payment.amount)) < 0.005
        except ValueError:
            amount_ok = False
        if not amount_ok:
            logger.error("Paynow amount mismatch on payment %s: %s", payment.pk, fields.get("amount"))
            payment.failure_reason = f"Amount mismatch: Paynow reported {fields.get('amount')}"
            payment.save(update_fields=["paynow_status", "paynow_reference", "failure_reason"])
            return payment.status
        payment.mark_paid()
        return Payment.PAID
    if lowered in FAILED_STATUSES | CANCELLED_STATUSES:
        payment.status = Payment.CANCELLED if lowered in CANCELLED_STATUSES else Payment.FAILED
        payment.failure_reason = status
        payment.save(update_fields=["status", "paynow_status", "paynow_reference", "failure_reason"])
        return payment.status
    payment.save(update_fields=["paynow_status", "paynow_reference"])
    return payment.status


def poll(payment):
    """Ask Paynow for the latest status (used when the result POST does not arrive)."""
    if not payment.poll_url or settings.PAYNOW_DRY_RUN:
        return payment.status
    if not payment.poll_url.startswith("https://www.paynow.co.zw/"):
        raise PaynowError("Unexpected poll URL")
    return apply_status(payment, _post(payment.poll_url, []))
