import hashlib
import hmac
import itertools
import json
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from complaint.models import Complain
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus
from parameters.models.models_transport_type import TransportType
from visit.models import Visit
from visit.tests import EstateFixture

from . import client
from .models import MessageLog, WhatsAppSession

SECRET = "test-app-secret"
RESIDENT_A = "263772111111"  # resident of stand 101 (stored as 0772111111)
RESIDENT_B = "263773222222"  # resident of stand 102
STRANGER = "263779999999"

_ids = itertools.count(1)


@override_settings(
    WHATSAPP_ENABLED=True,
    WHATSAPP_DRY_RUN=True,
    WHATSAPP_APP_SECRET=SECRET,
    WHATSAPP_VERIFY_TOKEN="verify-me",
    WHATSAPP_TEMPLATE_VISITOR_ARRIVED="",
)
class WhatsAppBotTests(EstateFixture):
    def setUp(self):
        super().setUp()
        client.OUTBOX.clear()
        self.walking = TransportType.objects.create(name="Walking")
        ComplaintStatus.objects.create(name="Pending")
        self.drainage = ComplaintCategory.objects.create(name="Drainage")

    # -- helpers ---------------------------------------------------------
    def post(self, body, signed=True):
        raw = json.dumps(body).encode()
        headers = {}
        if signed:
            headers["HTTP_X_HUB_SIGNATURE_256"] = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        return self.client.post("/whatsapp/webhook", data=raw, content_type="application/json", **headers)

    def send(self, wa_id, message, message_id=None):
        message = {"from": wa_id, "id": message_id or f"wamid.{next(_ids)}", "timestamp": "0", **message}
        body = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {"messages": [message]}}]}]}
        response = self.post(body)
        self.assertEqual(response.status_code, 200)
        return client.OUTBOX[-1] if client.OUTBOX else None

    def text(self, wa_id, body, **kw):
        return self.send(wa_id, {"type": "text", "text": {"body": body}}, **kw)

    def tap(self, wa_id, choice_id):
        return self.send(wa_id, {"type": "interactive", "interactive": {"type": "list_reply", "list_reply": {"id": choice_id, "title": ""}}})

    @staticmethod
    def body(message):
        if message["type"] == "text":
            return message["text"]["body"]
        return message["interactive"]["body"]["text"]

    @staticmethod
    def choice_ids(message):
        action = message["interactive"]["action"]
        if "buttons" in action:
            return [b["reply"]["id"] for b in action["buttons"]]
        return [row["id"] for section in action["sections"] for row in section["rows"]]

    def book(self, wa_id=RESIDENT_A, name="Chipo Banda", transport=None, reg="ABC 1234"):
        self.tap(wa_id, "book")
        reply = self.text(wa_id, name)
        transport = transport or self.transport
        self.assertIn(f"tr_{transport.id}", self.choice_ids(reply))
        reply = self.tap(wa_id, f"tr_{transport.id}")
        if "registration" in self.body(reply):
            reply = self.text(wa_id, reg)
        self.assertIn("confirm_yes", self.choice_ids(reply))
        self.tap(wa_id, "confirm_yes")
        return Visit.objects.latest("id")

    # -- webhook ---------------------------------------------------------
    def test_meta_verification_handshake(self):
        ok = self.client.get("/whatsapp/webhook", {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.content, b"12345")
        bad = self.client.get("/whatsapp/webhook", {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"})
        self.assertEqual(bad.status_code, 403)

    def test_unsigned_or_forged_requests_rejected(self):
        body = {"entry": [{"changes": [{"value": {"messages": [{"from": RESIDENT_A, "id": "x", "type": "text", "text": {"body": "hi"}}]}}]}]}
        self.assertEqual(self.post(body, signed=False).status_code, 403)
        forged = self.client.post("/whatsapp/webhook", data=json.dumps(body), content_type="application/json", HTTP_X_HUB_SIGNATURE_256="sha256=deadbeef")
        self.assertEqual(forged.status_code, 403)
        self.assertEqual(client.OUTBOX, [])

    @override_settings(WHATSAPP_ENABLED=False)
    def test_disabled_webhook_is_hidden(self):
        self.assertEqual(self.client.get("/whatsapp/webhook").status_code, 404)

    def test_duplicate_delivery_processed_once(self):
        self.text(RESIDENT_A, "hi", message_id="wamid.same")
        self.text(RESIDENT_A, "hi", message_id="wamid.same")
        self.assertEqual(len(client.OUTBOX), 1)
        self.assertEqual(MessageLog.objects.filter(direction="in").count(), 1)

    # -- identity --------------------------------------------------------
    def test_unregistered_number_turned_away(self):
        reply = self.text(STRANGER, "hi")
        self.assertIn("not registered", self.body(reply))
        self.tap(STRANGER, "book")
        self.assertEqual(Visit.objects.count(), 0)

    def test_greeting_shows_menu_with_address(self):
        reply = self.text(RESIDENT_A, "Hi")
        self.assertIn("101 Msasa Close", self.body(reply))
        self.assertEqual(self.choice_ids(reply), ["book", "visitors", "repair", "help"])

    # -- booking ---------------------------------------------------------
    def test_book_visitor_by_car(self):
        visit = self.book()
        self.assertEqual(visit.stand_number, 101)
        self.assertEqual(visit.home, "101 Msasa Close")
        self.assertEqual(visit.visitor_name, "Chipo Banda")
        self.assertEqual(visit.visitor_vehicle_reg_number, "ABC1234")
        self.assertEqual(visit.resident_phone_number, "0772111111")
        self.assertEqual(visit.visit_status, self.visit_status)
        confirmation = self.body(client.OUTBOX[-2])
        self.assertIn(visit.visit_code, confirmation)

    def test_book_visitor_walking_skips_registration(self):
        visit = self.book(transport=self.walking)
        self.assertIsNone(visit.visitor_vehicle_reg_number)

    def test_booking_lands_on_residents_own_stand(self):
        visit = self.book(wa_id=RESIDENT_B)
        self.assertEqual(visit.stand_number, 102)

    def test_cancel_mid_booking(self):
        self.tap(RESIDENT_A, "book")
        self.text(RESIDENT_A, "Chipo Banda")
        reply = self.text(RESIDENT_A, "menu")
        self.assertEqual(self.choice_ids(reply)[0], "book")
        self.assertEqual(Visit.objects.count(), 0)

    def test_stale_conversation_restarts(self):
        self.tap(RESIDENT_A, "book")
        WhatsAppSession.objects.filter(wa_id=RESIDENT_A).update(updated_at=timezone.now() - timedelta(hours=2))
        reply = self.text(RESIDENT_A, "Chipo Banda")
        self.assertEqual(self.choice_ids(reply)[0], "book")  # back at the menu, not asking for transport

    # -- my visitors -----------------------------------------------------
    def test_list_and_cancel_visitor(self):
        visit = self.book()
        reply = self.tap(RESIDENT_A, "visitors")
        self.assertIn(f"cancel_{visit.id}", self.choice_ids(reply))
        self.tap(RESIDENT_A, f"cancel_{visit.id}")
        visit.refresh_from_db()
        self.assertFalse(visit.status)

    def test_cannot_cancel_another_stands_visitor(self):
        visit = self.book(wa_id=RESIDENT_B)
        self.tap(RESIDENT_A, f"cancel_{visit.id}")
        visit.refresh_from_db()
        self.assertTrue(visit.status)

    # -- repairs ---------------------------------------------------------
    def test_report_repair(self):
        reply = self.tap(RESIDENT_A, "repair")
        self.assertIn(f"cat_{self.drainage.id}", self.choice_ids(reply))
        self.tap(RESIDENT_A, f"cat_{self.drainage.id}")
        reply = self.text(RESIDENT_A, "Blocked drain outside the gate")
        complaint = Complain.objects.get()
        self.assertEqual(complaint.stand_number, 101)
        self.assertEqual(complaint.complaint_category, self.drainage)
        self.assertEqual(complaint.description, "Blocked drain outside the gate")
        self.assertIn(complaint.complain_code, self.body(client.OUTBOX[-2]))

    # -- arrival notification -------------------------------------------
    def test_resident_told_when_guard_books_visitor_in(self):
        visit = self.book()
        client.OUTBOX.clear()
        self.client.force_authenticate(self.guard)
        response = self.client.put(f"/visit-book-in/{visit.id}", {"visitor_national_id": "63-222222D22", "visit_status": self.visit_status.id})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(client.OUTBOX), 1)
        self.assertEqual(client.OUTBOX[0]["to"], RESIDENT_A)
        self.assertIn("arrived at the gate", self.body(client.OUTBOX[0]))

    def test_no_message_outside_24h_window_without_template(self):
        visit = self.book()
        WhatsAppSession.objects.filter(wa_id=RESIDENT_A).update(last_inbound_at=timezone.now() - timedelta(days=2))
        client.OUTBOX.clear()
        self.client.force_authenticate(self.guard)
        self.client.put(f"/visit-book-in/{visit.id}", {"visitor_national_id": "63-222222D22", "visit_status": self.visit_status.id})
        self.assertEqual(client.OUTBOX, [])

    @override_settings(WHATSAPP_TEMPLATE_VISITOR_ARRIVED="visitor_arrived")
    def test_template_used_outside_24h_window(self):
        visit = self.book()
        WhatsAppSession.objects.filter(wa_id=RESIDENT_A).update(last_inbound_at=timezone.now() - timedelta(days=2))
        client.OUTBOX.clear()
        self.client.force_authenticate(self.guard)
        self.client.put(f"/visit-book-in/{visit.id}", {"visitor_national_id": "63-222222D22", "visit_status": self.visit_status.id})
        self.assertEqual(client.OUTBOX[0]["type"], "template")
        self.assertEqual(client.OUTBOX[0]["template"]["name"], "visitor_arrived")
