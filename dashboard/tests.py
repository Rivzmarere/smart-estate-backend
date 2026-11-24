from rest_framework.test import APITestCase

from authentication.models import User
from estates import sandbox_seed
from estates.models import Estate
from home.models import Home
from visit.models import Visit


class EstateDashboardTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gated, gated_logins = sandbox_seed.create_sandbox("Dash Park")
        cls.admin = User.objects.get(username=gated_logins[0][1])
        cls.guard = User.objects.get(username=gated_logins[1][1])
        cls.rental, rental_logins = sandbox_seed.create_sandbox("Dash Rentals", kind=Estate.RENTAL)
        cls.landlord = User.objects.get(username=rental_logins[0][1])
        cls.platform = User.objects.create_superuser(username="platform-dash", password="S3cure-pass!", role="Admin")

    def test_admin_sees_the_whole_estate(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["estate"]["slug"], self.gated.slug)
        self.assertEqual(data["counts"]["homes"], Home.all_estates.filter(estate=self.gated).count())
        self.assertEqual(data["summary"]["units"], 20)
        self.assertEqual(len(data["collected_by_month"]), 6)
        self.assertGreater(sum(float(m["amount"]) for m in data["collected_by_month"]), 0)
        inside = Visit.all_estates.filter(estate=self.gated, status=True, date_arrived__isnull=False, date_depature__isnull=True).count()
        self.assertEqual(data["gate"]["inside"], inside)
        self.assertTrue(data["repairs_by_status"])
        self.assertLessEqual(len(data["recent_repairs"]), 5)

    def test_guard_sees_only_the_gate(self):
        self.client.force_authenticate(self.guard)
        data = self.client.get("/dashboard").json()
        self.assertIn("gate", data)
        self.assertNotIn("summary", data)
        self.assertNotIn("collected_by_month", data)

    def test_rental_portfolio_has_no_gate(self):
        self.client.force_authenticate(self.landlord)
        data = self.client.get("/dashboard").json()
        self.assertNotIn("gate", data)
        self.assertEqual(data["bill_word"], "rent")
        self.assertEqual(data["summary"]["units"], 12)

    def test_only_the_users_own_estate(self):
        self.client.force_authenticate(self.landlord)
        data = self.client.get("/dashboard", HTTP_X_ESTATE=self.gated.slug).json()
        self.assertEqual(data["estate"]["slug"], self.rental.slug)

    def test_platform_must_choose_an_estate(self):
        self.client.force_authenticate(self.platform)
        self.assertEqual(self.client.get("/dashboard").status_code, 400)
        response = self.client.get("/dashboard", HTTP_X_ESTATE=self.gated.slug)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["estate"]["slug"], self.gated.slug)

    def test_needs_a_login(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 401)
