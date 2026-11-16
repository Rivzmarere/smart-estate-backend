"""
Check Paynow for payments still waiting, in case a result POST never arrived.
Run every few minutes from cron:  python manage.py paynow_poll
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from estates.context import use_estate
from levy import paynow
from levy.models import Payment
from levy.services import refresh_payment

# Paynow abandons a USSD prompt after a few minutes; give up after a day.
GIVE_UP_AFTER = timedelta(hours=24)


class Command(BaseCommand):
    help = "Poll Paynow for pending mobile-money payments"

    def handle(self, *args, **options):
        now = timezone.now()
        checked = 0
        pending = Payment.all_estates.filter(status=Payment.PENDING, created_at__lte=now - timedelta(minutes=1)).select_related("estate")
        for payment in pending:
            checked += 1
            with use_estate(payment.estate):
                self.check_payment(payment, now)
        self.stdout.write(f"Checked {checked} pending payment(s)")

    def check_payment(self, payment, now):
        try:
            refresh_payment(payment, give_up_after=GIVE_UP_AFTER)
        except paynow.PaynowError as exc:
            self.stderr.write(f"Payment {payment.pk}: {exc}")
