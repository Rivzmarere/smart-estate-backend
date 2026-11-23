from decimal import Decimal

from django.core.cache import cache
from rest_framework.test import APITestCase

from authentication.models import User
from estates import sandbox_seed
from estates.context import use_estate
from estates.models import Estate
from home.models import Home
from levy.accounts import account
from levy.models import Payment
from owner.models import Owner
from rentals.models import Lease
from resident.models import Resident
from stand.models import Stand

from .models import AuditEntry


class SupportTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.estate, logins = sandbox_seed.create_sandbox("Support Park")
        cls.admin = User.objects.get(username=logins[0][1])
        cls.guard = User.objects.get(username=logins[1][1])
        cls.rental, rental_logins = sandbox_seed.create_sandbox("Support Rentals", kind=Estate.RENTAL)
        cls.landlord = User.objects.get(username=rental_logins[0][1])

    def setUp(self):
        cache.clear()
        self.client.force_authenticate(self.admin)

    def home(self, **kw):
        return Home.all_estates.filter(estate=self.estate, status=True, **kw).select_related("stand", "owner", "resident").order_by("stand__stand_number").first()

    # ---------------------------------------------------------------- money

    def test_payment_recorded_and_reversed_with_history(self):
        home = self.home(resident__isnull=False)
        with use_estate(self.estate):
            before = account(home)["balance"]
        response = self.client.post("/levies/payments", {"home": home.id, "amount": "30", "currency": "USD", "method": "cash", "send_receipt": False})
        self.assertEqual(response.status_code, 201, response.content)
        payment = response.json()["id"]
        self.assertEqual(self.client.post(f"/levies/payments/{payment}/reverse", {"reason": ""}).status_code, 400)
        reversed_ = self.client.post(f"/levies/payments/{payment}/reverse", {"reason": "Wrong home"})
        self.assertEqual(reversed_.status_code, 200, reversed_.content)
        self.assertEqual(reversed_.json()["status"], Payment.CANCELLED)
        self.assertEqual(self.client.post(f"/levies/payments/{payment}/reverse", {"reason": "again"}).status_code, 400)
        with use_estate(self.estate):
            self.assertEqual(account(home)["balance"], before, "a reversed payment no longer counts")
        actions = list(AuditEntry.objects.filter(estate=self.estate).values_list("action", flat=True)[:2])
        self.assertEqual(actions, ["payment.reversed", "payment.recorded"])
        history = self.client.get("/audit?area=money").json()
        self.assertEqual(history["data"][0]["who"], "Demo Admin")
        self.assertIn("Wrong home", history["data"][0]["summary"])

    def test_history_is_per_estate_and_admin_only(self):
        self.client.post("/levies/rates", {"effective_from": "2026-01-01", "zig_per_usd": "27.10"})
        self.client.force_authenticate(self.landlord)
        self.assertFalse(any("27.10" in r["summary"] for r in self.client.get("/audit").json()["data"]))
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get("/audit").status_code, 403)

    # ---------------------------------------------------------------- users

    def test_admin_manages_staff(self):
        response = self.client.put(f"/users-details/{self.guard.id}", {"first_name": "Night", "role": "Admin", "is_active": False})
        self.assertEqual(response.status_code, 200, response.content)
        self.guard.refresh_from_db()
        self.assertEqual((self.guard.first_name, self.guard.role, self.guard.is_active), ("Night", "Admin", False))
        reset = self.client.post(f"/users-details/{self.guard.id}/reset-password")
        self.assertEqual(reset.status_code, 200)
        self.guard.refresh_from_db()
        self.assertTrue(self.guard.check_password(reset.json()["password"]))
        self.assertTrue(AuditEntry.objects.filter(action="user.password_reset", object_id=str(self.guard.id)).exists())
        self.assertNotIn(reset.json()["password"], str(list(AuditEntry.objects.values_list("summary", "details"))))

    def test_admin_cannot_lock_themselves_out(self):
        response = self.client.put(f"/users-details/{self.admin.id}", {"role": "Guard", "is_active": False})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"role", "is_active"})
        self.assertEqual(self.client.post(f"/users-details/{self.admin.id}/reset-password").status_code, 400)

    def test_switched_off_users_cannot_sign_in(self):
        self.client.put(f"/users-details/{self.guard.id}", {"is_active": False})
        self.guard.refresh_from_db()
        self.guard.set_password("Guard-pass-123!")
        self.guard.save()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/token", {"username": self.guard.username, "password": "Guard-pass-123!"}).status_code, 401)

    def test_other_estates_users_are_out_of_reach(self):
        self.assertEqual(self.client.put(f"/users-details/{self.landlord.id}", {"is_active": False}).status_code, 404)
        self.assertEqual(self.client.post(f"/users-details/{self.landlord.id}/reset-password").status_code, 404)

    # ---------------------------------------------------------------- archive instead of delete

    def test_removing_an_owner_never_removes_their_homes(self):
        home = self.home()
        response = self.client.delete(f"/owner/{home.owner_id}")
        self.assertEqual(response.status_code, 400)
        self.assertIn("still owns", response.json()["detail"])
        self.assertTrue(Home.all_estates.filter(pk=home.pk, status=True).exists())

    def test_removing_a_resident_empties_the_home(self):
        home = self.home(resident__isnull=False)
        resident = home.resident
        self.assertEqual(self.client.delete(f"/resident/{resident.id}").status_code, 204)
        home.refresh_from_db()
        resident.refresh_from_db()
        self.assertIsNone(home.resident)
        self.assertTrue(home.status, "the home stays")
        self.assertFalse(resident.status)
        self.assertNotIn(resident.id, [r["id"] for r in self.client.get("/resident").json()])

    def test_removing_a_home_keeps_its_payments(self):
        home = self.home()
        with use_estate(self.estate):
            payments = Payment.objects.filter(home=home).count()
        self.assertEqual(self.client.delete(f"/home/{home.id}").status_code, 204)
        home.refresh_from_db()
        self.assertFalse(home.status)
        with use_estate(self.estate):
            self.assertEqual(Payment.objects.filter(home=home).count(), payments)
        self.assertTrue(AuditEntry.objects.filter(action="home.removed", object_id=str(home.id)).exists())
        # The stand can go once its home is gone.
        self.assertEqual(self.client.delete(f"/stand/{home.stand_id}").status_code, 204)

    def test_a_stand_with_a_home_stays(self):
        home = self.home()
        self.assertEqual(self.client.delete(f"/stand/{home.stand_id}").status_code, 400)
        self.assertTrue(Stand.all_estates.get(pk=home.stand_id).status)

    def test_a_let_property_cannot_be_removed(self):
        self.client.force_authenticate(self.landlord)
        lease = Lease.all_estates.filter(estate=self.rental, status=Lease.ACTIVE).first()
        self.assertEqual(self.client.delete(f"/home/{lease.home_id}").status_code, 400)
        self.assertEqual(self.client.delete(f"/resident/{lease.tenant_id}").status_code, 400)


class PlatformUsageTests(APITestCase):
    def test_platform_sees_every_estate_others_cannot(self):
        estate, logins = sandbox_seed.create_sandbox("Usage Park")
        admin = User.objects.get(username=logins[0][1])
        platform = User.objects.create_superuser(username="usage-platform", password="S3cure-pass!", role="Admin")
        self.client.force_authenticate(platform)
        data = self.client.get("/platform/usage").json()
        row = next(r for r in data["estates"] if r["id"] == estate.id)
        self.assertEqual(row["homes"], 20)
        self.assertGreater(row["payments_30d"], 0)
        self.assertIn("monthly_bill_usd", data["totals"])
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/platform/usage").status_code, 403)


class SharedListTests(APITestCase):
    def test_removing_an_option_never_removes_records(self):
        from parameters.models.models_gender import Gender

        estate, _ = sandbox_seed.create_sandbox("Options Park")
        platform = User.objects.create_superuser(username="options-platform", password="S3cure-pass!", role="Admin")
        female = Gender.objects.get(name="Female")
        owners = Owner.all_estates.filter(gender=female).count()
        self.assertGreater(owners, 0)
        self.client.force_authenticate(platform)
        response = self.client.delete(f"/parameters/gender-category/{female.id}")
        self.assertEqual(response.status_code, 204, response.content)
        female.refresh_from_db()
        self.assertFalse(female.status)
        self.assertEqual(Owner.all_estates.filter(gender=female).count(), owners, "owners are untouched")
        self.assertNotIn(female.id, [g["id"] for g in self.client.get("/parameters/gender").json()])
