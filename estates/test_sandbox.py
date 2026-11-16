import datetime

from django.utils import timezone
from rest_framework.test import APITestCase

from authentication.models import User
from home.models import Home
from levy.models import Invoice, Payment
from sms import sender as sms
from visit.models import Visit
from whatsapp import client

from . import sandbox_seed
from .models import Estate, SandboxMessage


class SandboxTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.platform = User.objects.create_superuser(username="platform", password="S3cure-pass!", role="Admin")

    def setUp(self):
        sms.OUTBOX.clear()
        client.OUTBOX.clear()
        self.client.force_authenticate(self.platform)
        created = self.client.post("/estates/sandbox", {"name": "Demo Park"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.data = created.json()
        self.estate = Estate.objects.get(pk=self.data["id"])
        self.admin = User.objects.get(username=self.data["logins"][0]["username"])
        self.guard = User.objects.get(username=self.data["logins"][1]["username"])
        self.client.force_authenticate(None)

    def login(self, user):
        self.client.force_authenticate(User.objects.get(pk=user.pk))

    def test_sample_data_and_logins(self):
        self.assertTrue(self.estate.sandbox)
        self.assertEqual(Home.all_estates.filter(estate=self.estate).count(), 20)
        self.assertGreater(Visit.all_estates.filter(estate=self.estate).count(), 25)
        self.assertGreater(Invoice.all_estates.filter(estate=self.estate).count(), 40)
        login = self.client.post("/token", {"username": self.data["logins"][0]["username"], "password": self.data["logins"][0]["password"]}, format="json")
        self.assertEqual(login.status_code, 200)
        import jwt

        self.assertTrue(jwt.decode(login.json()["access"], options={"verify_signature": False})["sandbox"])
        self.login(self.admin)
        rows = {r["stand_number"]: r for r in self.client.get("/levies/accounts").json()["accounts"]}
        self.assertGreater(float(rows[103]["arrears"]), 0)  # some homes are behind on purpose

    def test_nothing_is_really_sent(self):
        self.login(self.guard)
        visit = Visit.all_estates.filter(estate=self.estate, date_arrived__isnull=True, status=True).first()
        response = self.client.post(f"/gate/visits/{visit.id}/book-in", {"visitor_national_id": "63-123456A78"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(sms.OUTBOX, [])
        self.assertEqual(client.OUTBOX, [])
        captured = SandboxMessage.all_estates.filter(estate=self.estate)
        self.assertIn("arrived at the gate", captured.latest("id").text)
        self.assertEqual(self.client.get("/sandbox/outbox").json()[0]["to"], captured.latest("id").to)

    def test_whatsapp_simulator(self):
        self.login(self.admin)
        menu = self.client.post("/sandbox/whatsapp", {"phone": "0771000101", "text": "hi"}, format="json").json()["replies"]
        self.assertEqual(menu[-1]["kind"], "list")
        self.assertIn("101 Acacia Drive", menu[-1]["text"])
        self.assertIn("book", [o["id"] for o in menu[-1]["options"]])
        reply = self.client.post("/sandbox/whatsapp", {"phone": "0771000101", "choice": "book"}, format="json").json()["replies"]
        self.assertIn("visitor's full name", reply[-1]["text"])

    def test_ussd_simulator(self):
        self.login(self.guard)
        screen = self.client.post("/sandbox/ussd", {"phone": "0771000101", "text": ""}, format="json").json()
        self.assertTrue(screen["continue"])
        self.assertIn("Book a visitor", screen["message"])

    def test_portal_shows_the_code(self):
        response = self.client.post("/resident/login/code", {"phone": "0771000101"}, format="json", HTTP_X_ESTATE=self.estate.slug)
        code = response.json()["sandbox_code"]
        self.assertEqual(len(code), 6)
        verified = self.client.post("/resident/login/verify", {"phone": "0771000101", "code": code}, format="json", HTTP_X_ESTATE=self.estate.slug)
        self.assertEqual(verified.status_code, 200)

    def test_payments_are_simulated(self):
        from portal import auth

        home = Home.all_estates.get(estate=self.estate, stand__stand_number=103)
        token = auth.make_token(self.estate, "+263771000103")
        self.client.credentials(HTTP_AUTHORIZATION=f"Resident {token}")
        started = self.client.post(f"/resident/homes/{home.id}/levy/pay", {"amount_usd": "45", "currency": "USD", "phone": "0771000103"}, format="json")
        self.assertEqual(started.status_code, 201, started.content)
        payment = Payment.all_estates.get(pk=started.json()["id"])
        Payment.all_estates.filter(pk=payment.pk).update(created_at=timezone.now() - datetime.timedelta(seconds=10))
        status = self.client.get(f"/resident/homes/{home.id}/levy/payments/{payment.id}").json()
        self.assertEqual(status["status"], "paid")
        self.assertTrue(status["receipt_number"])
        self.assertTrue(SandboxMessage.all_estates.filter(estate=self.estate, text__contains=status["receipt_number"]).exists())

    def test_real_numbers_never_reach_a_sandbox(self):
        from whatsapp.bot import find_home

        self.assertIsNone(find_home("263771000101"))  # a real WhatsApp message from this number
        from portal.access import homes_for_phone

        self.assertEqual(homes_for_phone("0771000101", across_estates=True), [])

    def test_reset_and_testers(self):
        self.login(self.admin)
        Visit.all_estates.filter(estate=self.estate).delete()
        self.assertEqual(self.client.post("/sandbox/reset").status_code, 200)
        self.assertGreater(Visit.all_estates.filter(estate=self.estate).count(), 25)
        self.assertEqual(Home.all_estates.filter(estate=self.estate).count(), 20)
        self.client.force_authenticate(self.platform)
        tester = self.client.post(f"/estates/{self.estate.id}/testers", {"role": "Guard", "label": "Tendai"}, format="json").json()
        self.assertTrue(tester["username"].endswith("-guard-tendai"))
        self.assertTrue(User.objects.get(username=tester["username"]).check_password(tester["password"]))

    def test_tools_only_in_a_sandbox(self):
        real = Estate.objects.get(slug="main")
        staff = User.objects.create_user(username="real_admin", password="S3cure-pass!", role="Admin", estate=real)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.post("/sandbox/ussd", {"phone": "0771000101", "text": ""}, format="json").status_code, 403)
        self.assertEqual(self.client.post("/estates/sandbox", {"name": "x"}, format="json").status_code, 403)
        self.client.force_authenticate(self.platform)
        self.assertEqual(self.client.post(f"/estates/{real.id}/reset").status_code, 404)
