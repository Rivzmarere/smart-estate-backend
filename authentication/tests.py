from django.core.cache import cache
from rest_framework.test import APITestCase

from estates.models import Estate
from smartEstateBackend.permissions import ROLE_GUARD

from .models import User


class MyAccountTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.estate = Estate.objects.create(name="Account Park", slug="account-park")
        cls.guard = User.objects.create_user(
            username="acc-guard", password="Old-pass-123!", role=ROLE_GUARD, estate=cls.estate, first_name="Gate", last_name="Guard"
        )

    def setUp(self):
        cache.clear()  # the login throttle counts password attempts
        self.client.force_authenticate(self.guard)

    def test_read_my_account(self):
        data = self.client.get("/account").json()
        self.assertEqual(data["username"], "acc-guard")
        self.assertEqual(data["role"], ROLE_GUARD)
        self.assertEqual(data["estate"], "Account Park")
        self.assertNotIn("password", data)

    def test_change_my_name_but_not_my_role(self):
        response = self.client.put("/account", {"first_name": " Tendai ", "last_name": "Moyo", "email": "T@Example.com", "role": "Admin", "username": "x"})
        self.assertEqual(response.status_code, 200, response.content)
        self.guard.refresh_from_db()
        self.assertEqual((self.guard.first_name, self.guard.email, self.guard.role, self.guard.username), ("Tendai", "t@example.com", ROLE_GUARD, "acc-guard"))
        self.assertEqual(self.client.put("/account", {"first_name": "", "email": "nope"}).status_code, 400)

    def test_change_my_password(self):
        bad = self.client.post("/account/password", {"old_password": "wrong", "new_password": "New-pass-456!"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("old_password", bad.json())
        weak = self.client.post("/account/password", {"old_password": "Old-pass-123!", "new_password": "123"})
        self.assertEqual(weak.status_code, 400)
        ok = self.client.post("/account/password", {"old_password": "Old-pass-123!", "new_password": "New-pass-456!"})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.guard.refresh_from_db()
        self.assertTrue(self.guard.check_password("New-pass-456!"))

    def test_needs_a_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/account").status_code, 401)
        self.assertEqual(self.client.post("/account/password", {}).status_code, 401)


class LastLoginTests(APITestCase):
    def test_signing_in_records_the_time(self):
        cache.clear()
        user = User.objects.create_user(username="ll-user", password="Some-pass-123!", role=ROLE_GUARD)
        self.assertIsNone(user.last_login)
        self.assertEqual(self.client.post("/token", {"username": "ll-user", "password": "Some-pass-123!"}).status_code, 200)
        user.refresh_from_db()
        self.assertIsNotNone(user.last_login)
