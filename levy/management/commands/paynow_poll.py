"""
Check Paynow for payments still waiting, in case a result POST never arrived.
Run every few minutes from cron:  python manage.py paynow_poll
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from levy import paynow
from levy.models import Payment
from levy.notifications import send_payment_failed, send_receipt

# Paynow abandons a USSD prompt after a few minutes; give up after a day.
GIVE_UP_AFTER = timedelta(hours=24)


class Command(BaseCommand):
    help = "Poll Paynow for pending mobile-money payments"

    def handle(self, *args, **options):
        now = timezone.now()
        checked = 0
        for payment in Payment.objects.filter(status=Payment.PENDING, created_at__lte=now - timedelta(minutes=1)):
            checked += 1
            try:
                with transaction.atomic():
                    locked = Payment.objects.select_for_update().get(pk=payment.pk)
                    if locked.status != Payment.PENDING:
                        continue
                    status = paynow.poll(locked)
                    if status == Payment.PENDING and locked.created_at < now - GIVE_UP_AFTER:
                        locked.status = Payment.FAILED
                        locked.failure_reason = "No answer from Paynow within 24 hours"
                        locked.save(update_fields=["status", "failure_reason"])
                        status = Payment.FAILED
            except paynow.PaynowError as exc:
                self.stderr.write(f"Payment {payment.pk}: {exc}")
                continue
            if status == Payment.PAID:
                send_receipt(locked)
            elif status in (Payment.FAILED, Payment.CANCELLED):
                send_payment_failed(locked)
        self.stdout.write(f"Checked {checked} pending payment(s)")
