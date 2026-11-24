import datetime

from django.utils import timezone

from estates.models import Estate
from parameters.models.models_provider_category import ProviderCategory
from provider.models import Provider
from sms import sender as sms
from whatsapp import client
from whatsapp.models import WhatsAppSession
from whatsapp.tests import RESIDENT_A, RESIDENT_B, BotCase

from .models import Conversation, ConversationMessage, EmergencyAlert


class EmergencyTests(BotCase):
    def setUp(self):
        super().setUp()
        Estate.objects.filter(slug="main").update(name="Msasa Park", emergency_phones="0771000111, 0712000222", office_phone="0242123456")

    def test_sos_alerts_security_by_sms_and_on_the_gate(self):
        reply = self.text(RESIDENT_A, "SOS")
        self.assertIn("em_security", self.choice_ids(reply))
        reply = self.tap(RESIDENT_A, "em_security")
        self.assertIn("Alert sent to estate security", self.body(reply))
        self.assertIn("Police 995", self.body(reply))
        self.assertIn("0242123456", self.body(reply))

        alert = EmergencyAlert.objects.get()
        self.assertEqual((alert.kind, alert.stand_number, alert.status), ("security", 101, "open"))
        self.assertEqual({m["to"] for m in sms.OUTBOX[-2:]}, {"+263771000111", "+263712000222"})
        self.assertIn("101 Msasa Close", sms.OUTBOX[-1]["message"])

        self.text(RESIDENT_A, "Two men at the back wall")
        alert.refresh_from_db()
        self.assertIn("back wall", alert.details)
        self.assertIn("back wall", sms.OUTBOX[-1]["message"])

        # The guard sees it and responds; the resident is told.
        self.client.force_authenticate(self.guard)
        listed = self.client.get("/alerts").json()
        self.assertEqual((listed[0]["id"], listed[0]["phone"]), (alert.id, "0772111111"))
        acknowledged = self.client.post(f"/alerts/{alert.id}/acknowledge").json()
        self.assertEqual(acknowledged["status"], "acknowledged")
        self.assertIn("is responding", self.body(client.OUTBOX[-1]))
        self.client.post(f"/alerts/{alert.id}/resolve")
        alert.refresh_from_db()
        self.assertEqual(alert.status, "resolved")

    def test_repeat_alert_is_not_duplicated(self):
        self.text(RESIDENT_A, "emergency")
        self.tap(RESIDENT_A, "em_medical")
        self.tap(RESIDENT_A, "emergency")
        reply = self.tap(RESIDENT_A, "em_medical")
        self.assertIn("already has your alert", self.body(reply))
        self.assertEqual(EmergencyAlert.objects.count(), 1)

    def test_typing_instead_of_tapping_still_raises_an_alert(self):
        self.text(RESIDENT_A, "sos")
        self.text(RESIDENT_A, "my neighbour collapsed")
        alert = EmergencyAlert.objects.get()
        self.assertEqual(alert.kind, "other")
        self.assertIn("collapsed", alert.details)

    def test_cancel(self):
        self.text(RESIDENT_A, "sos")
        self.tap(RESIDENT_A, "em_cancel")
        self.assertFalse(EmergencyAlert.objects.exists())

    def test_residents_cannot_see_alerts(self):
        self.assertEqual(self.client.get("/alerts").status_code, 401)


class ProviderDirectoryTests(BotCase):
    def test_lists_providers_by_category_without_id_numbers(self):
        plumbing = ProviderCategory.objects.create(name="Plumbing")
        ProviderCategory.objects.create(name="Unused category")
        Provider.objects.create(name="Blessing", surname="Mhlanga", address="Harare", id_number="63-777777X77",
                                phone_number1="0778555666", provider_category=plumbing, authorized_by=self.admin)
        reply = self.tap(RESIDENT_A, "providers")
        self.assertEqual(self.choice_ids(reply), [f"pc_{plumbing.id}", "back"])
        self.tap(RESIDENT_A, f"pc_{plumbing.id}")
        listing = self.body(client.OUTBOX[-2])
        self.assertIn("Blessing Mhlanga: 0778555666", listing)
        self.assertNotIn("63-777777X77", listing)

    def test_no_providers(self):
        reply = self.tap(RESIDENT_A, "providers")
        self.assertIn("not listed any service providers", self.body(reply))


class OfficeChatTests(BotCase):
    def setUp(self):
        super().setUp()
        Estate.objects.filter(slug="main").update(office_phone="0772999000", office_hours="Mon-Fri 08:00-16:30")

    def test_resident_writes_and_office_replies(self):
        reply = self.tap(RESIDENT_A, "office")
        self.assertIn("Mon-Fri 08:00-16:30", self.body(reply))
        self.assertIn("wants to chat", sms.OUTBOX[-1]["message"])  # office alerted once
        self.text(RESIDENT_A, "Hello, my gate remote is broken")  # "hello" must not reset to the menu
        reply = self.text(RESIDENT_A, "Can I get a new one?")
        conversation = Conversation.objects.get()
        self.assertEqual(conversation.unread, 2)
        self.assertEqual(list(conversation.messages.values_list("text", flat=True)), ["Hello, my gate remote is broken", "Can I get a new one?"])

        self.client.force_authenticate(self.admin)
        inbox = self.client.get("/inbox").json()
        self.assertEqual((inbox["unread"], inbox["conversations"][0]["last_message"]["text"]), (2, "Can I get a new one?"))
        detail = self.client.get(f"/inbox/{conversation.id}").json()
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(self.client.get("/inbox").json()["unread"], 0)

        sent = self.client.post(f"/inbox/{conversation.id}/reply", {"text": "Yes, collect it at the office for $10."}, format="json").json()
        self.assertTrue(sent["delivered"])
        self.assertIn("collect it at the office", self.body(client.OUTBOX[-1]))
        self.assertEqual(client.OUTBOX[-1]["to"], RESIDENT_A)

        self.client.post(f"/inbox/{conversation.id}/close")
        self.assertEqual(WhatsAppSession.objects.get(wa_id=RESIDENT_A).state, "menu")
        self.assertIn("closed this chat", self.body(client.OUTBOX[-1]))

    def test_menu_leaves_the_chat_and_reply_brings_resident_back(self):
        self.tap(RESIDENT_A, "office")
        self.text(RESIDENT_A, "Question about levies")
        reply = self.text(RESIDENT_A, "menu")
        self.assertIn("back with the Smart Estate assistant", self.body(reply))
        conversation = Conversation.objects.get()
        self.client.force_authenticate(self.admin)
        self.client.post(f"/inbox/{conversation.id}/reply", {"text": "What is your question?"}, format="json")
        self.text(RESIDENT_A, "How much is it?")
        self.assertEqual(conversation.messages.filter(direction="in").count(), 2)

    def test_reply_after_24_hours_warns_the_office(self):
        self.tap(RESIDENT_A, "office")
        self.text(RESIDENT_A, "Hi")
        WhatsAppSession.objects.filter(wa_id=RESIDENT_A).update(last_inbound_at=timezone.now() - datetime.timedelta(days=2))
        conversation = Conversation.objects.get()
        self.client.force_authenticate(self.admin)
        sent = self.client.post(f"/inbox/{conversation.id}/reply", {"text": "Sorry for the delay"}, format="json").json()
        self.assertFalse(sent["delivered"])
        self.assertIn("phone them on 0772111111", sent["warning"])

    def test_guards_cannot_read_the_inbox(self):
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get("/inbox").status_code, 403)

    def test_each_resident_has_their_own_conversation(self):
        self.tap(RESIDENT_A, "office")
        self.text(RESIDENT_A, "From A")
        self.tap(RESIDENT_B, "office")
        self.text(RESIDENT_B, "From B")
        self.assertEqual(Conversation.objects.count(), 2)
        self.assertEqual(ConversationMessage.objects.filter(conversation__wa_id=RESIDENT_B).get().text, "From B")
