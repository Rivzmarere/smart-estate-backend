"""
Daily job for rental portfolios: bill the month's rent and remind tenants.
    python manage.py rent_run
Rent for a month is billed a week before the month starts, so tenants see it
before it is due. Safe to run as often as you like: nothing is billed or
sent twice.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from estates.context import use_estate
from estates.models import Estate
from rentals import services


class Command(BaseCommand):
    help = "Bill monthly rent and send rent reminders for every rental portfolio"

    def add_arguments(self, parser):
        parser.add_argument("--no-reminders", action="store_true", help="Bill only; send nothing")

    def handle(self, *args, **options):
        today = timezone.localdate()
        periods = {services.month_start(today), services.month_start(today + services.BILL_AHEAD)}
        for estate in Estate.objects.filter(active=True, kind=Estate.RENTAL):
            with use_estate(estate):
                billed = sum(services.bill_rent(period)[0] for period in sorted(periods))
                reminded = 0 if options["no_reminders"] else services.send_rent_reminders(today)
            self.stdout.write(f"{estate.name}: {billed} rent invoice(s), {reminded} reminder(s)")
