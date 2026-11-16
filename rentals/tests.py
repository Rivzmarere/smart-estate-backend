"""Managing agents and landlords: organisations, rental portfolios, leases, rent and statements."""

import datetime
from decimal import Decimal
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from authentication.models import User
from estates.context import use_estate
from estates.models import Estate, Organisation
from home.models import Home
from levy.models import Invoice, Payment
from portal import auth
from portal.access import homes_for_phone
from sms import sender as sms
from ussd.menu import handle as ussd
from whatsapp import client
from whatsapp.bot import menu_rows

from . import services
from .models import Lease

PASSWORD = "S3cure-pass!"
TENANT = "0774555111"


class RentalFixture(APITestCase):
    """An agent with one rental portfolio, reached the way the back office does (X-Estate header)."""

    def setUp(self):
        sms.OUTBOX.clear()
        client.OUTBOX.clear()
        self.today = timezone.localdate()
        self.platform = User.objects.create_superuser(username="platform", password=PASSWORD, role="Admin")
        self.org = Organisation.objects.create(name="Kopje Property Managers", kind=Organisation.AGENT)
        self.agent = User.objects.create_user(username="agent", password=PASSWORD, role="Admin", organisation=self.org)
        self.client.force_authenticate(self.agent)
        created = self.client.post("/organisation/estates", {"name": "Avenues Flats", "kind": "rental", "management_fee_percent": "10"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.portfolio = Estate.objects.get(pk=created.json()["id"])
        self.slug = self.portfolio.slug

    def api(self, method, path, data=None, slug=None, **extra):
        return getattr(self.client, method)(path, data, format="json", HTTP_X_ESTATE=slug or self.slug, **extra)

    def add_property(self, address="Flat 1, 12 Baines Avenue", **owner):
        owner = owner or {"owner_name": "Tawanda", "owner_surname": "Makoni", "owner_phone": "0772000900"}
        response = self.api("post", "/rentals/properties", {"address": address, **owner})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["home_id"]

    def start_lease(self, home_id, phone=TENANT, rent="400", start=None, **more):
        body = {"home": home_id, "tenant_name": "Chipo", "tenant_surname": "Banda", "tenant_phone": phone,
                "start_date": (start or self.today.replace(day=1)).isoformat(), "rent_usd": rent, **more}
        response = self.api("post", "/rentals/leases", body)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()


class OrganisationTests(RentalFixture):
    def test_token_says_who_they_work_for(self):
        import jwt

        self.client.force_authenticate(None)
        login = self.client.post("/token", {"username": "agent", "password": PASSWORD}, format="json")
        claims = jwt.decode(login.json()["access"], options={"verify_signature": False})
        self.assertEqual(claims["organisation"], "Kopje Property Managers")
        self.assertFalse(claims["platform"])

    def test_agent_sees_only_their_own_estates(self):
        other = Organisation.objects.create(name="Rival Agents")
        theirs = Estate.objects.create(name="Rival Court", slug="rival-court", kind=Estate.RENTAL, organisation=other)
        rival = User.objects.create_user(username="rival", password=PASSWORD, role="Admin", organisation=other)
        self.client.force_authenticate(rival)
        self.client.post("/rentals/properties", {"address": "1 Rival Road", "owner_name": "A", "owner_surname": "B", "owner_phone": "0772000901"},
                         format="json", HTTP_X_ESTATE=theirs.slug)
        self.client.force_authenticate(self.agent)
        self.assertEqual([e["slug"] for e in self.client.get("/organisation").json()["estates"]], [self.slug])
        # Asking for another customer's estate gives nothing, and nothing can be written there.
        self.assertEqual(self.api("get", "/rentals/properties", slug="rival-court").json()["properties"], [])
        blocked = self.api("post", "/rentals/properties", {"address": "x", "owner_name": "A", "owner_surname": "B", "owner_phone": "0772000902"}, slug="rival-court")
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(Home.all_estates.filter(estate=theirs).count(), 1)
        self.assertEqual(self.api("get", "/levies/accounts", slug="main").json()["accounts"], [])

    def test_only_platform_staff_manage_organisations(self):
        self.assertEqual(self.client.get("/organisations").status_code, 403)
        self.assertEqual(self.client.get("/estates").status_code, 403)
        self.client.force_authenticate(self.platform)
        made = self.client.post("/organisations", {"name": "Mr Moyo's houses", "kind": "landlord", "price_per_unit_usd": "2.00"}, format="json")
        self.assertEqual(made.status_code, 201, made.content)
        login = self.client.post(f"/organisations/{made.json()['id']}/admin", {"username": "moyo", "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 201, login.content)
        self.assertTrue(User.objects.get(username="moyo").spans_organisation)

    def test_staff_for_the_organisation_and_for_one_estate(self):
        colleague = self.client.post("/organisation/staff", {"username": "colleague", "password": PASSWORD}, format="json")
        self.assertEqual(colleague.status_code, 201, colleague.content)
        self.assertTrue(User.objects.get(username="colleague").spans_organisation)
        clerk = self.client.post("/organisation/staff", {"username": "clerk", "password": PASSWORD, "estate": self.portfolio.id}, format="json")
        self.assertEqual(User.objects.get(username="clerk").estate, self.portfolio)
        self.assertEqual(clerk.json()["estate"], "Avenues Flats")
        main = Estate.objects.get(slug="main")
        self.assertEqual(self.client.post("/organisation/staff", {"username": "sneaky", "password": PASSWORD, "estate": main.id}, format="json").status_code, 400)
        self.assertEqual(len(self.client.get("/organisation/staff").json()), 3)

    def test_switched_off_organisation_cannot_sign_in_or_read(self):
        self.add_property()
        Organisation.objects.filter(pk=self.org.pk).update(active=False)
        self.agent.refresh_from_db()
        self.client.force_authenticate(self.agent)
        self.assertEqual(self.api("get", "/rentals/properties").json()["properties"], [])
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/token", {"username": "agent", "password": PASSWORD}, format="json").status_code, 401)

    def test_overview_adds_up_every_estate(self):
        home = self.add_property()
        self.add_property("Flat 2, 12 Baines Avenue")
        self.start_lease(home)
        gated = self.client.post("/organisation/estates", {"name": "Msasa Park", "kind": "estate"}, format="json").json()
        body = self.client.get("/organisation/overview").json()
        self.assertEqual(body["totals"]["estates"], 2)
        self.assertEqual(body["totals"]["units"], 2)
        rows = {r["slug"]: r for r in body["estates"]}
        self.assertEqual(rows[self.slug]["occupied"], 1)
        self.assertEqual(rows[self.slug]["vacant"], 1)
        self.assertEqual(Decimal(rows[self.slug]["monthly_rent"]), Decimal("400"))
        self.assertEqual(rows[gated["slug"]]["units"], 0)


class LeaseTests(RentalFixture):
    def test_lease_bills_rent_and_shows_on_the_rent_roll(self):
        home = self.add_property()
        lease = self.start_lease(home, deposit_usd="400", deposit_paid_usd="400")
        with use_estate(self.portfolio):
            invoice = Invoice.objects.get(lease_id=lease["id"])
            self.assertEqual((invoice.kind, invoice.amount_usd, invoice.period), (Invoice.RENT, Decimal("400.00"), self.today.replace(day=1)))
            self.assertEqual(Home.objects.get(pk=home).resident.phone_number1, TENANT)
        body = self.api("get", "/rentals/properties").json()
        row = body["properties"][0]
        self.assertEqual((row["tenant"], row["state"], Decimal(row["balance"])), ("Chipo Banda", "let", Decimal("400")))
        self.assertEqual(Decimal(row["deposit_held_usd"]), Decimal("400"))
        self.assertEqual(body["totals"]["let"], 1)
        # A second lease on the same property is refused.
        again = self.api("post", "/rentals/leases", {"home": home, "tenant_name": "A", "tenant_surname": "B", "tenant_phone": "0774555222",
                                                     "start_date": self.today.isoformat(), "rent_usd": "300"})
        self.assertEqual(again.status_code, 400)

    def test_part_month_and_billing_run(self):
        home = self.add_property()
        lease = self.start_lease(home, start=self.today, first_rent_usd="150")
        with use_estate(self.portfolio):
            self.assertEqual(Invoice.objects.get(lease_id=lease["id"]).amount_usd, Decimal("150.00"))
        following = services.next_month(self.today).strftime("%Y-%m")
        preview = self.api("post", "/rentals/bill", {"period": following, "preview": True}).json()
        self.assertEqual(preview["to_create"], 1)
        self.assertEqual(self.api("post", "/rentals/bill", {"period": following}).json()["created"], 1)
        self.assertEqual(self.api("post", "/rentals/bill", {"period": following}).json()["created"], 0)

    def test_payment_statement_and_owner_statement(self):
        home = self.add_property()
        lease = self.start_lease(home)
        paid = self.api("post", f"/rentals/leases/{lease['id']}/payments", {"amount": "250", "currency": "USD", "method": "cash"})
        self.assertEqual(paid.status_code, 201, paid.content)
        self.assertIn("receipt", sms.OUTBOX[-1]["message"].lower())
        self.api("post", "/rentals/expenses", {"home": home, "category": "repairs", "description": "Geyser element", "amount_usd": "60"})
        detail = self.api("get", f"/rentals/leases/{lease['id']}").json()
        self.assertEqual(Decimal(detail["balance"]), Decimal("150"))
        self.assertEqual(len(detail["statement"]), 2)
        statement = self.api("get", "/rentals/statement").json()
        row = statement["properties"][0]
        self.assertEqual([Decimal(row[k]) for k in ("income", "expenses", "fee", "net")], [Decimal("250"), Decimal("60"), Decimal("25"), Decimal("165")])
        self.assertEqual(Decimal(statement["totals"]["net"]), Decimal("165"))
        owner_id = self.api("get", "/rentals/people").json()["owners"][0]["id"]
        mine = self.api("get", f"/rentals/statement?owner={owner_id}").json()
        self.assertEqual(mine["owner"]["name"], "Tawanda Makoni")
        self.assertEqual(len(mine["properties"]), 1)

    def test_moving_out_and_the_next_tenant_starts_clean(self):
        home = self.add_property()
        first = self.start_lease(home, deposit_usd="400", deposit_paid_usd="400")
        too_much = self.api("post", f"/rentals/leases/{first['id']}/end", {"ended_on": self.today.isoformat(), "deposit_returned_usd": "300", "deposit_deducted_usd": "200"})
        self.assertEqual(too_much.status_code, 400)
        ended = self.api("post", f"/rentals/leases/{first['id']}/end", {"ended_on": self.today.isoformat(), "deposit_returned_usd": "100", "deposit_deducted_usd": "300", "reason": "Moved to Bulawayo"})
        self.assertEqual(ended.status_code, 200, ended.content)
        self.assertEqual(Decimal(ended.json()["balance"]), Decimal("100"))  # 400 rent less 300 kept from the deposit
        with use_estate(self.portfolio):
            self.assertIsNone(Home.objects.get(pk=home).resident)
        self.assertEqual(homes_for_phone(TENANT, across_estates=True), [])  # the old tenant is locked out

        second = self.start_lease(home, phone="0774555333", rent="450")
        with use_estate(self.portfolio):
            acc = services.lease_account(Lease.objects.get(pk=second["id"]))
        self.assertEqual(acc["balance"], Decimal("450.00"))
        # The new tenant's portal shows none of the old tenant's payments.
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Resident {auth.make_token(self.portfolio, '+263774555333')}")
        levy = self.client.get(f"/resident/homes/{home}/levy").json()
        self.assertEqual(Decimal(levy["balance"]), Decimal("450"))
        self.assertEqual(levy["payments"], [])
        self.client.credentials()
        self.client.force_authenticate(self.agent)
        history = self.api("get", f"/rentals/properties/{home}").json()
        self.assertEqual([l["status"] for l in history["leases"]], ["active", "ended"])
        # The past tenant can still settle what they owe.
        settle = self.api("post", f"/rentals/leases/{first['id']}/payments", {"amount": "100", "currency": "USD", "method": "ecocash", "send_receipt": False})
        self.assertEqual(settle.status_code, 201, settle.content)
        self.assertEqual(Decimal(self.api("get", f"/rentals/leases/{first['id']}").json()["balance"]), Decimal("0"))
        self.assertEqual(Decimal(self.api("get", f"/rentals/leases/{second['id']}").json()["balance"]), Decimal("450"))

    def test_agreement_upload(self):
        lease = self.start_lease(self.add_property())
        path = f"/rentals/leases/{lease['id']}/document"
        bad = self.client.post(path, {"file": SimpleUploadedFile("lease.exe", b"MZ\x90\x00 not a document")}, format="multipart", HTTP_X_ESTATE=self.slug)
        self.assertEqual(bad.status_code, 400)
        with self.settings(MEDIA_ROOT=self.enterContext(__import__("tempfile").TemporaryDirectory())):
            good = self.client.post(path, {"file": SimpleUploadedFile("lease.pdf", b"%PDF-1.4 signed agreement")}, format="multipart", HTTP_X_ESTATE=self.slug)
            self.assertEqual(good.status_code, 200, good.content)
            self.assertTrue(good.json()["has_document"])
            fetched = self.api("get", path)
            self.assertEqual(fetched["Content-Type"], "application/pdf")
            self.assertEqual(b"".join(fetched.streaming_content), b"%PDF-1.4 signed agreement")
            self.client.force_authenticate(None)
            self.assertEqual(self.client.get(path, HTTP_X_ESTATE=self.slug).status_code, 401)


class TenantChannelTests(RentalFixture):
    def setUp(self):
        super().setUp()
        self.home = self.add_property()
        self.lease = self.start_lease(self.home)

    def test_no_gate_features_and_rent_wording(self):
        self.assertEqual(homes_for_phone(TENANT, across_estates=True, action="visitors"), [])
        keep_open, screen = ussd("+263774555111", "")
        self.assertTrue(keep_open)
        self.assertIn("Rent balance", screen)
        self.assertNotIn("visitor", screen.lower())
        self.assertNotIn("Emergency", screen)
        ids = [row[0] for row in menu_rows(self.portfolio)]
        self.assertIn("levy", ids)
        self.assertNotIn("book", ids)
        self.assertNotIn("emergency", ids)
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Resident {auth.make_token(self.portfolio, '+263774555111')}")
        me = self.client.get("/resident/me").json()
        self.assertEqual(me["estate"]["kind"], "rental")
        self.assertFalse(me["homes"][0]["can"]["visitors"])
        self.assertTrue(me["homes"][0]["can"]["levy"])
        self.assertEqual(self.client.post(f"/resident/homes/{self.home}/emergency", {"kind": "fire"}, format="json").status_code, 404)

    def test_daily_run_bills_and_reminds_once(self):
        with use_estate(self.portfolio):
            Invoice.objects.filter(lease_id=self.lease["id"]).update(due_date=self.today - datetime.timedelta(days=5))
        out = StringIO()
        call_command("rent_run", stdout=out)
        self.assertIn("Avenues Flats", out.getvalue())
        reminders = [m for m in sms.OUTBOX if "overdue" in m["message"]]
        self.assertEqual(len(reminders), 1)
        self.assertIn("USD 400.00", reminders[0]["message"])
        call_command("rent_run", stdout=StringIO())
        self.assertEqual(len([m for m in sms.OUTBOX if "overdue" in m["message"]]), 1)
        with use_estate(self.portfolio):
            # Next month's rent is billed a week ahead, never twice.
            self.assertLessEqual(Invoice.objects.filter(lease_id=self.lease["id"], kind=Invoice.RENT).count(), 2)

    def test_reminders_can_be_switched_off(self):
        Estate.objects.filter(pk=self.portfolio.pk).update(rent_reminders=False)
        with use_estate(Estate.objects.get(pk=self.portfolio.pk)):
            Invoice.objects.filter(lease_id=self.lease["id"]).update(due_date=self.today - datetime.timedelta(days=5))
            self.assertEqual(services.send_rent_reminders(self.today), 0)

    @override_settings(PAYNOW_DRY_RUN=True, PAYNOW_USD_INTEGRATION_ID="1001", PAYNOW_USD_INTEGRATION_KEY="k", PAYNOW_AUTH_EMAIL="m@example.com",
                       PUBLIC_API_URL="https://api.test")
    def test_tenant_pays_rent_from_the_portal(self):
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Resident {auth.make_token(self.portfolio, '+263774555111')}")
        started = self.client.post(f"/resident/homes/{self.home}/levy/pay", {"amount_usd": "400", "currency": "USD", "phone": TENANT}, format="json")
        self.assertEqual(started.status_code, 201, started.content)
        with use_estate(self.portfolio):
            self.assertEqual(Payment.objects.get(pk=started.json()["id"]).lease_id, self.lease["id"])
