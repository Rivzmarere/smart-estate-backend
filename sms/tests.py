from django.test import SimpleTestCase, override_settings

from visit.tests import EstateFixture

from . import sender
from .models import SmsLog


class ZimbabweMobileTests(SimpleTestCase):
    def test_formats_accepted(self):
        for raw in ["0772111111", "0772 111 111", "+263 772 111 111", "263772111111", "772111111", "0712345678", "0733123456", "0782123456"]:
            self.assertTrue(sender.zimbabwe_mobile(raw), raw)
        self.assertEqual(sender.zimbabwe_mobile("0772 111 111"), "+263772111111")

    def test_rejected(self):
        for raw in ["", None, "+447700900123", "0242123456", "07721", "+27821234567"]:
            self.assertIsNone(sender.zimbabwe_mobile(raw), raw)


@override_settings(SMS_BACKEND="console")
class PortalSmsTests(EstateFixture):
    def setUp(self):
        super().setUp()
        sender.OUTBOX.clear()

    def test_portal_booking_texts_visitor(self):
        response = self.client.post("/visit", {**self.booking(101, "0772111111"), "visitor_phone_number": "0712 345 678"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["data"]["sms_sent"])
        code = response.data["data"]["visit_code"]
        self.assertEqual(sender.OUTBOX[-1]["to"], "+263712345678")
        self.assertIn(code, sender.OUTBOX[-1]["message"])
        self.assertEqual(SmsLog.objects.count(), 1)

    def test_portal_booking_without_phone_sends_nothing(self):
        response = self.client.post("/visit", self.booking(101, "0772111111"))
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["data"]["sms_sent"])
        self.assertEqual(sender.OUTBOX, [])

    def test_foreign_number_rejected(self):
        response = self.client.post("/visit", {**self.booking(101, "0772111111"), "visitor_phone_number": "+447700900123"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(sender.OUTBOX, [])

    @override_settings(SMS_BACKEND="twilio", TWILIO_ACCOUNT_SID="x", TWILIO_AUTH_TOKEN="y")
    def test_provider_failure_does_not_break_booking(self):
        from unittest import mock
        with mock.patch.dict(sender.BACKENDS, {"twilio": mock.Mock(side_effect=RuntimeError("down"))}):
            response = self.client.post("/visit", {**self.booking(101, "0772111111"), "visitor_phone_number": "0712345678"})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["data"]["sms_sent"])
        self.assertFalse(SmsLog.objects.get().ok)
