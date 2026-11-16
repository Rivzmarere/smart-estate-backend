import datetime
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone

from assist.models import EmergencyAlert
from complaint.models import Complain
from home.models import Home
from levy import paynow
from levy.models import Invoice, Payment
from levy.tests import PAYNOW
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus
from sms import sender as sms
from visit.models import Visit
from visit.tests import EstateFixture

SECRET = "ussd-test-secret"


@override_settings(USSD_SECRET=SECRET, **PAYNOW)
class UssdTests(EstateFixture):
    def setUp(self):
        super().setUp()
        sms.OUTBOX.clear()
        paynow.OUTBOX.clear()
        self.session = 0

    def dial(self, text, phone="+263772111111"):
        response = self.client.post(f"/ussd/{SECRET}", {"sessionId": "s1", "serviceCode": "*384#", "phoneNumber": phone, "text": text})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertLessEqual(len(body) - 4, 182, body)  # one USSD screen
        return body

    def test_wrong_secret_or_disabled(self):
        self.assertEqual(self.client.post("/ussd/guess", {"phoneNumber": "+263772111111", "text": ""}).status_code, 404)
        with self.settings(USSD_SECRET=""):
            self.assertEqual(self.client.post(f"/ussd/{SECRET}", {"phoneNumber": "+263772111111", "text": ""}).status_code, 404)

    def test_unregistered_number(self):
        self.assertTrue(self.dial("", phone="+263779999999").startswith("END This number is not registered"))

    def test_main_menu(self):
        body = self.dial("")
        self.assertTrue(body.startswith("CON "))
        self.assertIn("1. Book a visitor", body)
        self.assertIn("Emergency", body)

    def test_book_a_visitor(self):
        self.assertIn("Visitor's full name", self.dial("1"))
        self.assertIn("mobile number", self.dial("1*Chipo Banda"))
        self.assertIn("Book Chipo Banda", self.dial("1*Chipo Banda*0"))  # one transport type: no question
        self.assertFalse(Visit.objects.exists())  # nothing happens before the last step
        body = self.dial("1*Chipo Banda*0*1")
        self.assertTrue(body.startswith("END Booked. Gate code: "))
        visit = Visit.objects.get()
        self.assertEqual((visit.stand_number, visit.visitor_name), (101, "Chipo Banda"))
        self.assertIn(visit.visit_code, sms.OUTBOX[-1]["message"])  # the code also comes by SMS

    def test_my_visitors(self):
        self.dial("1*Chipo Banda*0*1")
        self.assertIn("Chipo Banda", self.dial("2"))

    def test_levy_pay_all(self):
        home = Home.objects.get(stand__stand_number=101)
        Invoice.objects.create(home=home, stand_number=101, address=home.address, period=datetime.date(2026, 11, 1),
                               description="Levy", amount_usd=Decimal("45.00"), due_date=timezone.localdate())
        self.assertIn("Balance USD 45.00", self.dial("3"))
        self.assertIn("Pay USD 45.00 from 0772111111 (EcoCash)", self.dial("3*1"))
        body = self.dial("3*1*1")
        self.assertIn("Approve the EcoCash prompt", body)
        self.assertEqual(Payment.objects.get().amount, Decimal("45.00"))
        self.assertEqual(paynow.OUTBOX[-1]["phone"], "0772111111")

    def test_report_fault(self):
        ComplaintStatus.objects.create(name="Pending")
        ComplaintCategory.objects.create(name="Water")
        body = self.dial("4*Burst pipe at the gate")
        self.assertIn("reference", body)
        self.assertEqual(Complain.objects.get().description, "Burst pipe at the gate")

    def test_emergency(self):
        body = self.dial("5*1")
        self.assertIn("Alert sent to estate security", body)
        self.assertEqual(EmergencyAlert.objects.get().kind, "security")

    def test_owner_chooses_the_home_first(self):
        body = self.dial("", phone="+263771000001")
        self.assertIn("Choose your home", body)
        self.assertIn("Book a visitor", self.dial("2", phone="+263771000001"))
