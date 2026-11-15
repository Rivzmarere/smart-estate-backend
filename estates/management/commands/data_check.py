"""
Find data that will confuse residents, guards or the WhatsApp bot. Run before
going live and after importing an estate:  python manage.py data_check
"""

import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from authentication.models import User
from estates.models import Estate
from home.models import Home
from resident.models import Resident
from sms.sender import zimbabwe_mobile

PHONE_FIELDS = ("phone_number1", "phone_number2", "phone_number3", "phone_number4")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")


class Command(BaseCommand):
    help = "List data problems to fix before going live"

    def handle(self, *args, **options):
        problems = 0

        def report(estate, text):
            nonlocal problems
            problems += 1
            self.stdout.write(f"[{estate}] {text}")

        for estate in Estate.objects.all():
            homes = Home.all_estates.filter(estate=estate, status=True).select_related("stand", "resident")
            seen_stands = defaultdict(list)
            for home in homes:
                seen_stands[home.stand.stand_number].append(home)
                if not home.address.strip() or TIMESTAMP.match(home.address):
                    report(estate, f"Home {home.id} (stand {home.stand.stand_number}) has no real address: {home.address!r}")
                if home.resident is None:
                    report(estate, f"Home {home.id} (stand {home.stand.stand_number}, {home.address}) has no resident: nobody can book visitors or use WhatsApp for it")
            for stand, on_stand in seen_stands.items():
                if len(on_stand) > 1:
                    report(estate, f"Stand {stand} has {len(on_stand)} active homes ({', '.join(str(h.id) for h in on_stand)}): bookings for it are ambiguous")

            numbers = defaultdict(set)
            for resident in Resident.all_estates.filter(estate=estate, status=True):
                usable = [n for n in (getattr(resident, f) for f in PHONE_FIELDS) if n]
                if not any(zimbabwe_mobile(n) for n in usable):
                    report(estate, f"Resident {resident.id} {resident.name} {resident.surname} has no Zimbabwean mobile number: no WhatsApp or SMS")
                for n in usable:
                    normalised = zimbabwe_mobile(n)
                    if normalised:
                        numbers[normalised].add(resident)
            for number, people in numbers.items():
                if len(people) > 1:
                    names = ", ".join(f"{r.id} {r.name} {r.surname}" for r in people)
                    report(estate, f"{number} belongs to {len(people)} residents ({names}): WhatsApp will use the first home it finds")

            if not estate.emergency_numbers:
                report(estate, "No emergency numbers: WhatsApp emergencies will only show on the gate screen and in the Inbox")
            if not estate.office_phone:
                report(estate, "No office phone: residents are not shown how to reach the office")

        if Estate.objects.count() > 1:
            for user in User.objects.filter(estate__isnull=True, is_superuser=False, is_active=True):
                report("all", f"User {user.username} has no estate and cannot see any data")

        self.stdout.write(self.style.SUCCESS("No problems found") if not problems else self.style.WARNING(f"{problems} problem(s)"))
