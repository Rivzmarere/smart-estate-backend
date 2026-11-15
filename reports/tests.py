import datetime as dt

from django.utils import timezone

from visit.models import Visit
from visit.tests import EstateFixture


class GateDailyReportTests(EstateFixture):
    def visit(self, name, **kw):
        return Visit.objects.create(
            stand_number=101, home="101 Msasa Close", visit_code=name[:6].upper(), visitor_name=name,
            transport_type=self.transport, visit_status=self.visit_status, **kw,
        )

    def test_admin_only(self):
        self.assertEqual(self.client.get("/reports/gate-daily").status_code, 401)
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get("/reports/gate-daily").status_code, 403)

    def test_counts_for_today(self):
        now = timezone.now()
        self.visit("Came and left", date_arrived=now, date_depature=now, authorized_by=self.guard)
        self.visit("Still inside", date_arrived=now, authorized_by=self.guard)
        self.visit("No show")
        self.visit("Cancelled one", status=False)
        old = self.visit("Yesterday")
        Visit.objects.filter(id=old.id).update(date_created=now - dt.timedelta(days=2))

        self.client.force_authenticate(self.admin)
        data = self.client.get("/reports/gate-daily").data
        self.assertEqual(data["totals"]["booked"], 4)
        self.assertEqual(data["totals"]["arrived"], 2)
        self.assertEqual(data["totals"]["departed"], 1)
        self.assertEqual(data["totals"]["still_inside"], 1)
        self.assertEqual(data["totals"]["no_show"], 1)
        self.assertEqual(data["totals"]["cancelled"], 1)
        self.assertEqual(sum(data["arrivals_by_hour"]), 2)
        names = {v["visitor_name"]: v for v in data["visits"]}
        self.assertNotIn("Yesterday", names)
        self.assertEqual(names["Still inside"]["state"], "Inside")
        self.assertEqual(names["Still inside"]["booked_in_by"], "guard1")

    def test_bad_date(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/reports/gate-daily?date=15-11-2026").status_code, 400)
