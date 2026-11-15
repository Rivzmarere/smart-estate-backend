"""Two estates on one installation must never see each other's data."""

import datetime
from decimal import Decimal

from django.test import override_settings

from authentication.models import User
from home.models import Home
from levy.models import Invoice
from owner.models import Owner
from resident.models import Resident
from stand.models import Stand
from visit.models import Visit
from visit.tests import EstateFixture
from whatsapp import client
from whatsapp.tests import BotCase

from .context import use_estate
from .models import Estate


def build_second_estate(fixture, name="Borrowdale Brooke", slug="borrowdale"):
    """Estate B with its own stand 101 (same number as estate A's) and resident 0774333333."""
    first_home = Home.all_estates.get(stand__stand_number=101)
    estate = Estate.objects.create(name=name, slug=slug)
    with use_estate(estate):
        owner = Owner.objects.create(
            name="Kuda", surname="Sibanda", id_number="63-999999Z99", date_of_birth=datetime.date(1975, 1, 1),
            gender=first_home.owner.gender, nationality=first_home.owner.nationality, phone_number1="0774333333",
            phone_number2="", email="kuda@example.com", authorized_by=fixture.admin,
        )
        resident = Resident.objects.create(
            name="Kuda", surname="Sibanda", id_number="63-999999Z99", date_of_birth=datetime.date(1975, 1, 1),
            gender=first_home.owner.gender, nationality=first_home.owner.nationality, phone_number1="0774333333",
            authorized_by=fixture.admin,
        )
        stand = Stand.objects.create(stand_number=101, stand_status=first_home.stand.stand_status, authorized_by=fixture.admin)
        home = Home.objects.create(owner=owner, stand=stand, address="101 Brooke Drive", resident=resident,
                                   home_status=first_home.home_status, authorized_by=fixture.admin)
        Visit.objects.create(stand_number=101, home=home.address, visit_code="BBB111", resident_phone_number="0774333333",
                             visitor_name="Brooke Visitor", transport_type=fixture.transport, visit_status=fixture.visit_status)
    return estate, home


class TwoEstates(EstateFixture):
    def setUp(self):
        super().setUp()
        self.estate_a = Estate.objects.get(slug="main")
        User.objects.filter(pk__in=[self.admin.pk, self.guard.pk]).update(estate=self.estate_a)
        self.admin.refresh_from_db()
        self.guard.refresh_from_db()
        with use_estate(self.estate_a):
            self.home_a = Home.objects.get(stand__stand_number=101)
            Visit.objects.create(stand_number=101, home=self.home_a.address, visit_code="AAA111", resident_phone_number="0772111111",
                                 visitor_name="Main Visitor", transport_type=self.transport, visit_status=self.visit_status)
        self.estate_b, self.home_b = build_second_estate(self)
        self.admin_b = User.objects.create_user(username="admin_b", password="S3cure-pass!", role="Admin", estate=self.estate_b)
        self.guard_b = User.objects.create_user(username="guard_b", password="S3cure-pass!", role="Guard", estate=self.estate_b)


class IsolationTests(TwoEstates):
    def test_lists_only_show_own_estate(self):
        self.client.force_authenticate(self.admin_b)
        homes = self.client.get("/home").json()
        self.assertEqual([h["address"] for h in homes], ["101 Brooke Drive"])
        stands = self.client.get("/stand").json()
        self.assertEqual(len(stands), 1)
        self.client.force_authenticate(self.admin)
        self.assertEqual(len(self.client.get("/home").json()), 2)

    def test_cannot_open_another_estates_record(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/home/{self.home_b.id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/home/{self.home_b.id}").status_code, 404)
        self.assertTrue(Home.all_estates.filter(pk=self.home_b.pk).exists())

    def test_gate_list_is_per_estate(self):
        self.client.force_authenticate(self.guard_b)
        codes = [v["visit_code"] for v in self.client.get("/gate/expected").json()["data"]]
        self.assertEqual(codes, ["BBB111"])
        visit_a = Visit.all_estates.get(visit_code="AAA111")
        response = self.client.post(f"/gate/visits/{visit_a.id}/book-in", {"visitor_national_id": "63-1"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_estate_cannot_be_set_by_the_client(self):
        self.client.force_authenticate(self.admin)
        status_id = self.home_a.stand.stand_status_id
        self.client.post("/stand", {"stand_number": 306, "stand_status": status_id, "authorized_by": self.admin.id, "estate": self.estate_b.id}, format="json")
        self.assertEqual(Stand.all_estates.get(stand_number=306).estate, self.estate_a)

    def test_who_did_it_comes_from_the_login(self):
        self.client.force_authenticate(self.admin_b)
        status_id = self.home_b.stand.stand_status_id
        # The old screens send authorized_by=1; it must be ignored.
        self.client.post("/stand", {"stand_number": 407, "stand_status": status_id, "authorized_by": self.admin.id}, format="json")
        self.assertEqual(Stand.all_estates.get(stand_number=407).authorized_by, self.admin_b)

    def test_shared_lists_need_platform_staff_once_there_are_two_estates(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/parameters/gender").status_code, 200)
        self.assertEqual(self.client.post("/parameters/gender", {"name": "Other"}, format="json").status_code, 403)
        platform = User.objects.create_superuser(username="platform2", password="S3cure-pass!", role="Admin")
        self.client.force_authenticate(platform)
        self.assertIn(self.client.post("/parameters/gender", {"name": "Other"}, format="json").status_code, (200, 201))

    def test_new_records_belong_to_the_creators_estate(self):
        self.client.force_authenticate(self.admin_b)
        status_id = self.home_b.stand.stand_status_id
        response = self.client.post("/stand", {"stand_number": 205, "stand_status": status_id, "authorized_by": self.admin_b.id}, format="json")
        self.assertIn(response.status_code, (200, 201), response.content)
        self.assertEqual(Stand.all_estates.get(stand_number=205).estate, self.estate_b)

    def test_cannot_point_at_another_estates_home(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/levies/invoices", {"home": self.home_b.id, "kind": "other", "description": "x", "amount_usd": "5", "due_date": "2026-12-01"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Invoice.all_estates.exists())

    def test_users_are_per_estate(self):
        self.client.force_authenticate(self.admin_b)
        names = {u["username"] for u in self.client.get("/users-all").json()}
        self.assertEqual(names, {"admin_b", "guard_b"})
        response = self.client.post("/users-signUp", {"username": "guard_b2", "password": "S3cure-pass!", "role": "Guard"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(username="guard_b2").estate, self.estate_b)

    def test_public_portal_picks_estate_by_slug(self):
        booking = self.booking(101, "0774333333")
        self.assertEqual(self.client.post("/visit", booking, format="json").status_code, 400)  # no estate given
        response = self.client.post("/visit", booking, format="json", HTTP_X_ESTATE="borrowdale")
        self.assertEqual(response.status_code, 201, response.content)
        visit = Visit.all_estates.latest("id")
        self.assertEqual((visit.estate, visit.home), (self.estate_b, "101 Brooke Drive"))
        # Estate A's resident cannot book through estate B
        wrong = self.client.post("/visit", self.booking(101, "0772111111"), format="json", HTTP_X_ESTATE="borrowdale")
        self.assertEqual(wrong.status_code, 400)

    def test_public_estate_info(self):
        self.assertEqual(self.client.get("/estate/public?estate=borrowdale").json()["name"], "Borrowdale Brooke")
        self.assertEqual(self.client.get("/estate/public?estate=nope").status_code, 404)

    def test_token_names_the_estate(self):
        import jwt

        token = self.client.post("/token", {"username": "admin_b", "password": "S3cure-pass!"}, format="json").json()["access"]
        claims = jwt.decode(token, options={"verify_signature": False})
        self.assertEqual((claims["estate"], claims["estate_slug"], claims["platform"]), ("Borrowdale Brooke", "borrowdale", False))


class PlatformTests(TwoEstates):
    def setUp(self):
        super().setUp()
        self.platform = User.objects.create_superuser(username="platform", password="S3cure-pass!", role="Admin")

    def test_only_platform_staff_manage_estates(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/estates").status_code, 403)
        self.client.force_authenticate(self.platform)
        self.assertEqual(len(self.client.get("/estates").json()), 2)

    def test_create_estate_and_its_admin(self):
        self.client.force_authenticate(self.platform)
        created = self.client.post("/estates", {"name": "Mt Pleasant Heights", "office_phone": "0242000000"}, format="json")
        self.assertEqual(created.status_code, 201)
        estate_id = created.json()["id"]
        self.assertEqual(created.json()["slug"], "mt-pleasant-heights")
        admin = self.client.post(f"/estates/{estate_id}/admin", {"username": "mph_admin", "password": "S3cure-pass!"}, format="json")
        self.assertEqual(admin.status_code, 201)
        user = User.objects.get(username="mph_admin")
        self.assertEqual((user.role, user.estate_id), ("Admin", estate_id))

    def test_switched_off_estate_loses_access(self):
        self.client.force_authenticate(self.platform)
        self.client.patch(f"/estates/{self.estate_b.id}", {"active": False}, format="json")
        self.client.force_authenticate(None)
        login = self.client.post("/token", {"username": "admin_b", "password": "S3cure-pass!"}, format="json")
        self.assertEqual(login.status_code, 401)
        self.client.force_authenticate(User.objects.get(pk=self.admin_b.pk))  # an old token still in use
        self.assertEqual(self.client.get("/home").json(), [])
        self.assertEqual(self.client.get("/estate/public?estate=borrowdale").status_code, 404)

    def test_platform_sees_all_or_one_estate(self):
        self.client.force_authenticate(self.platform)
        self.assertEqual(len(self.client.get("/home").json()), 3)
        self.assertEqual(len(self.client.get("/home", HTTP_X_ESTATE="borrowdale").json()), 1)

    def test_secret_keys_are_never_returned(self):
        self.client.force_authenticate(self.admin_b)
        response = self.client.put("/estate", {"paynow_usd_integration_id": "777", "paynow_usd_integration_key": "s3cret"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("paynow_usd_integration_key", response.json())
        self.assertTrue(response.json()["paynow_usd_ready"])
        # Leaving the key blank keeps it
        self.client.put("/estate", {"paynow_usd_integration_key": ""}, format="json")
        self.estate_b.refresh_from_db()
        self.assertEqual(self.estate_b.paynow_usd_integration_key, "s3cret")
        self.assertNotIn("s3cret", self.client.get("/estate").content.decode())


@override_settings(PAYNOW_DRY_RUN=True, PAYNOW_USD_INTEGRATION_ID="", PAYNOW_USD_INTEGRATION_KEY="")
class BotAcrossEstates(BotCase):
    def setUp(self):
        super().setUp()
        self.estate_b, self.home_b = build_second_estate(self)

    def test_resident_is_served_in_their_own_estate(self):
        reply = self.text("263774333333", "hi")
        self.assertIn("Borrowdale Brooke", self.body(reply))
        self.assertIn("101 Brooke Drive", self.body(reply))
        visit = self.book(wa_id="263774333333", visitor_phone="skip")
        self.assertEqual((visit.estate, visit.home), (self.estate_b, "101 Brooke Drive"))

    def test_my_visitors_does_not_mix_estates(self):
        self.tap("263774333333", "visitors")
        rows = self.choice_ids(client.OUTBOX[-1])
        visit_b = Visit.all_estates.get(visit_code="BBB111")
        self.assertIn(f"cancel_{visit_b.id}", rows)
        self.assertEqual(len(rows), 2)  # BBB111 + back

    def test_each_estate_has_its_own_paynow_account(self):
        from levy import paynow
        from levy.models import Payment

        Estate.objects.filter(pk=self.estate_b.pk).update(paynow_usd_integration_id="9001", paynow_usd_integration_key="kb")
        self.estate_b.refresh_from_db()
        self.assertEqual(paynow.available_currencies(self.estate_b), [Payment.USD])
        self.assertEqual(paynow.available_currencies(Estate.objects.get(slug="main")), [])
        with use_estate(self.estate_b):
            Invoice.objects.create(home=self.home_b, stand_number=101, address=self.home_b.address, period=datetime.date(2026, 11, 1),
                                   description="Levy", amount_usd=Decimal("30"), due_date=datetime.date(2026, 11, 7))
        self.tap("263774333333", "levy")
        self.tap("263774333333", "levy_all")
        self.text("263774333333", "0774333333")
        self.assertEqual(paynow.OUTBOX[-1]["id"], "9001")
        self.assertEqual(Payment.all_estates.get().estate, self.estate_b)
