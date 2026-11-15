import datetime

from django.core.cache import cache
from rest_framework.test import APITestCase

from authentication.models import User
from home.models import Home
from owner.models import Owner
from parameters.models.models_gender import Gender
from parameters.models.models_home_status import HomeStatus
from parameters.models.models_nationality import Nationality
from parameters.models.models_provider_category import ProviderCategory
from parameters.models.models_stand_status import StandStatus
from parameters.models.models_transport_type import TransportType
from parameters.models.models_visit_status import VisitStatus
from provider.models import Provider
from resident.models import Resident
from stand.models import Stand
from visit.models import Visit
from visit.utilities import CODE_LENGTH, phone_variants


class EstateFixture(APITestCase):
    """Two stands, each with one resident, plus an admin and a guard."""

    def setUp(self):
        cache.clear()  # reset throttle counters between tests
        self.admin = User.objects.create_user(username="admin1", password="S3cure-pass!", role="Admin")
        self.guard = User.objects.create_user(username="guard1", password="S3cure-pass!", role="Guard")

        gender = Gender.objects.create(name="Female")
        nationality = Nationality.objects.create(name="Zimbabwean")
        stand_status = StandStatus.objects.create(name="Occupied")
        home_status = HomeStatus.objects.create(name="Occupied")
        self.transport = TransportType.objects.create(name="Car")
        self.visit_status = VisitStatus.objects.create(name="Expected")

        owner = Owner.objects.create(
            name="Tendai", surname="Moyo", id_number="63-123456A78", date_of_birth=datetime.date(1980, 1, 1),
            gender=gender, nationality=nationality, phone_number1="0771000001", phone_number2="",
            email="owner@example.com", authorized_by=self.admin,
        )
        self.resident_a = Resident.objects.create(
            name="Rudo", surname="Ncube", id_number="63-654321B21", date_of_birth=datetime.date(1990, 5, 5),
            gender=gender, nationality=nationality, phone_number1="0772111111", authorized_by=self.admin,
        )
        self.resident_b = Resident.objects.create(
            name="Farai", surname="Dube", id_number="63-111111C11", date_of_birth=datetime.date(1985, 3, 3),
            gender=gender, nationality=nationality, phone_number1="0773222222", authorized_by=self.admin,
        )
        stand_a = Stand.objects.create(stand_number=101, stand_status=stand_status, authorized_by=self.admin)
        stand_b = Stand.objects.create(stand_number=102, stand_status=stand_status, authorized_by=self.admin)
        Home.objects.create(owner=owner, stand=stand_a, address="101 Msasa Close", resident=self.resident_a,
                            home_status=home_status, authorized_by=self.admin)
        Home.objects.create(owner=owner, stand=stand_b, address="102 Msasa Close", resident=self.resident_b,
                            home_status=home_status, authorized_by=self.admin)

    def booking(self, stand, phone):
        return {
            "stand_number": stand,
            "resident_phone_number": phone,
            "visitor_name": "Chipo Banda",
            "transport_type": self.transport.id,
            "visit_status": self.visit_status.id,
        }


class AccessControlTests(EstateFixture):
    def test_anonymous_cannot_read_private_data(self):
        for url in ["/resident", "/owner", "/home", "/stand", "/visit", "/users-all", "/white-list-guest", "/complain"]:
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_anonymous_cannot_create_users(self):
        response = self.client.post("/users-signUp", {"username": "x", "password": "S3cure-pass!", "role": "Admin"})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(User.objects.filter(username="x").exists())

    def test_guard_can_read_but_not_change_residents(self):
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get("/resident").status_code, 200)
        self.assertEqual(self.client.delete(f"/resident/{self.resident_a.id}").status_code, 403)
        self.assertTrue(Resident.objects.filter(id=self.resident_a.id).exists())

    def test_guard_cannot_manage_users(self):
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get("/users-all").status_code, 403)

    def test_admin_can_create_guard(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/users-signUp", {"username": "guard2", "password": "An0ther-pass!", "role": "Guard"})
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.data["data"])

    def test_unknown_role_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/users-signUp", {"username": "boss", "password": "An0ther-pass!", "role": "Owner"})
        self.assertEqual(response.status_code, 400)

    def test_password_hash_never_returned(self):
        self.client.force_authenticate(self.admin)
        body = self.client.get("/resident").content.decode()
        self.assertNotIn("pbkdf2", body)
        self.assertNotIn("password", body)

    def test_missing_record_returns_404(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/resident/99999").status_code, 404)

    def test_login_returns_jwt_with_role(self):
        response = self.client.post("/token", {"username": "guard1", "password": "S3cure-pass!"})
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(self.client.get("/visit").status_code, 200)

    def test_public_reference_lists_are_readable(self):
        self.assertEqual(self.client.get("/parameters/transport-type").status_code, 200)
        self.assertEqual(self.client.post("/parameters/transport-type", {"name": "Bus"}).status_code, 401)

    def test_public_provider_list_hides_id_numbers(self):
        category = ProviderCategory.objects.create(name="Plumber")
        Provider.objects.create(name="Tawanda", surname="Sibanda", address="Harare", id_number="63-999999Z99",
                                phone_number1="0774333333", provider_category=category, authorized_by=self.admin)
        body = self.client.get("/service-provider").content.decode()
        self.assertIn("Tawanda", body)
        self.assertNotIn("63-999999Z99", body)


class VisitorBookingTests(EstateFixture):
    def test_resident_books_own_stand(self):
        response = self.client.post("/visit", self.booking(101, "0772111111"))
        self.assertEqual(response.status_code, 201)
        code = response.data["data"]["visit_code"]
        self.assertEqual(len(code), CODE_LENGTH)
        visit = Visit.objects.get(visit_code=code)
        self.assertEqual(visit.home, "101 Msasa Close")
        self.assertIsNone(visit.date_depature)

    def test_international_phone_format_matches(self):
        response = self.client.post("/visit", self.booking(101, "+263 772 111 111"))
        self.assertEqual(response.status_code, 201)

    def test_resident_cannot_book_into_another_stand(self):
        # Resident A's number must not unlock stand 102.
        response = self.client.post("/visit", self.booking(102, "0772111111"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Visit.objects.count(), 0)

    def test_unknown_stand_rejected(self):
        self.assertEqual(self.client.post("/visit", self.booking(999, "0772111111")).status_code, 400)

    def test_guard_books_in_and_out(self):
        code = self.client.post("/visit", self.booking(101, "0772111111")).data["data"]["visit_code"]
        visit = Visit.objects.get(visit_code=code)
        self.client.force_authenticate(self.guard)

        response = self.client.put(f"/visit-book-in/{visit.id}", {
            "visitor_national_id": "63-222222D22", "visit_status": self.visit_status.id,
        })
        self.assertEqual(response.status_code, 201, response.data)
        visit.refresh_from_db()
        self.assertEqual(visit.authorized_by, self.guard)
        self.assertIsNotNone(visit.date_arrived)
        self.assertIsNone(visit.date_depature)

        response = self.client.put(f"/visit-book-out/{visit.id}", {"visit_status": self.visit_status.id})
        self.assertEqual(response.status_code, 201)
        visit.refresh_from_db()
        self.assertIsNotNone(visit.date_depature)
        self.assertFalse(visit.status)

    def test_anonymous_cannot_book_in(self):
        code = self.client.post("/visit", self.booking(101, "0772111111")).data["data"]["visit_code"]
        visit = Visit.objects.get(visit_code=code)
        self.assertEqual(self.client.put(f"/visit-book-in/{visit.id}", {}).status_code, 401)


class PhoneVariantTests(APITestCase):
    def test_variants(self):
        self.assertIn("0772111111", phone_variants("+263772111111"))
        self.assertIn("+263772111111", phone_variants("0772 111 111"))
        self.assertEqual(phone_variants(""), set())


class GateScreenTests(EstateFixture):
    def setUp(self):
        super().setUp()
        self.inside = VisitStatus.objects.create(name="Inside")
        self.departed = VisitStatus.objects.create(name="departed")
        code = self.client.post("/visit", self.booking(101, "0772111111")).data["data"]["visit_code"]
        self.visit = Visit.objects.get(visit_code=code)
        self.client.force_authenticate(self.guard)

    def test_expected_list(self):
        response = self.client.get("/gate/expected")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"][0]["visit_code"], self.visit.visit_code)
        self.assertEqual(response.data["data"][0]["transport"], "Car")

    def test_anonymous_blocked(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/gate/expected").status_code, 401)

    def test_book_in_and_out(self):
        response = self.client.post(f"/gate/visits/{self.visit.id}/book-in", {"visitor_national_id": "63-222222 d22"})
        self.assertEqual(response.status_code, 201)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.visit_status, self.inside)
        self.assertEqual(self.visit.visitor_national_id, "63-222222 D22")
        self.assertEqual(self.visit.authorized_by, self.guard)

        response = self.client.post(f"/gate/visits/{self.visit.id}/book-out", {})
        self.assertEqual(response.status_code, 201)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.visit_status, self.departed)
        self.assertFalse(self.visit.status)
        self.assertGreaterEqual(self.visit.date_depature, self.visit.date_arrived)
        self.assertEqual(self.client.get("/gate/expected").data["data"], [])

    def test_replayed_actions_are_harmless(self):
        url = f"/gate/visits/{self.visit.id}/book-in"
        first = self.client.post(url, {"visitor_national_id": "63-222222D22"})
        arrived = Visit.objects.get(id=self.visit.id).date_arrived
        again = self.client.post(url, {"visitor_national_id": "63-222222D22"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.data["already"])
        self.assertEqual(Visit.objects.get(id=self.visit.id).date_arrived, arrived)

    def test_offline_time_is_kept(self):
        from django.utils import timezone
        earlier = timezone.now() - datetime.timedelta(minutes=40)
        self.client.post(f"/gate/visits/{self.visit.id}/book-in", {"visitor_national_id": "63-222222D22", "at": earlier.isoformat()})
        self.visit.refresh_from_db()
        self.assertAlmostEqual(self.visit.date_arrived.timestamp(), earlier.timestamp(), delta=1)

    def test_future_or_ancient_times_rejected(self):
        from django.utils import timezone
        url = f"/gate/visits/{self.visit.id}/book-in"
        future = (timezone.now() + datetime.timedelta(hours=1)).isoformat()
        ancient = (timezone.now() - datetime.timedelta(days=5)).isoformat()
        self.assertEqual(self.client.post(url, {"visitor_national_id": "63-2D22", "at": future}).status_code, 400)
        self.assertEqual(self.client.post(url, {"visitor_national_id": "63-2D22", "at": ancient}).status_code, 400)

    def test_id_number_required(self):
        response = self.client.post(f"/gate/visits/{self.visit.id}/book-in", {})
        self.assertEqual(response.status_code, 400)

    def test_cancelled_booking_cannot_enter(self):
        Visit.objects.filter(id=self.visit.id).update(status=False)
        response = self.client.post(f"/gate/visits/{self.visit.id}/book-in", {"visitor_national_id": "63-222222D22"})
        self.assertEqual(response.status_code, 409)
