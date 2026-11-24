import datetime
import shutil
import tempfile

from django.test import override_settings
from django.utils import timezone

from complaint.models import Complain, ComplaintPhoto
from parameters.models.models_complaint_status import ComplaintStatus
from sms import sender as sms
from visit.models import Visit
from whatsapp import client
from whatsapp.models import WhatsAppSession
from whatsapp.tests import RESIDENT_A, RESIDENT_B, BotCase

from .models import WalkInRequest


class WalkInTests(BotCase):
    def ask(self, stand=101, name="Tatenda Shumba"):
        self.client.force_authenticate(self.guard)
        response = self.client.post("/gate/walk-ins", {"stand_number": stand, "visitor_name": name, "vehicle": "aec 1234"}, format="json")
        self.client.force_authenticate(None)
        return response

    def test_guard_asks_resident_who_approves_on_whatsapp(self):
        self.text(RESIDENT_A, "hi")  # resident talked to the bot recently, so a normal message is allowed
        response = self.ask()
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["whatsapp_sent"])
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["vehicle"], "AEC1234")
        question = client.OUTBOX[-1]
        self.assertEqual(question["to"], RESIDENT_A)
        self.assertIn("Tatenda Shumba", self.body(question))
        self.assertEqual(self.choice_ids(question), [f"walkin_yes_{data['id']}", f"walkin_no_{data['id']}"])

        reply = self.tap(RESIDENT_A, f"walkin_yes_{data['id']}")
        self.assertIn("Approved", self.body(reply))
        walk_in = WalkInRequest.objects.get()
        self.assertEqual(walk_in.status, "approved")
        visit = walk_in.visit
        self.assertEqual((visit.stand_number, visit.visitor_name), (101, "Tatenda Shumba"))
        self.assertIn(visit.visit_code, self.body(reply))

        # The gate sees the answer and the new visit is on the expected list.
        self.client.force_authenticate(self.guard)
        polled = self.client.get(f"/gate/walk-ins/{walk_in.id}").json()
        self.assertEqual((polled["status"], polled["visit_code"]), ("approved", visit.visit_code))
        expected = self.client.get("/gate/expected").json()["data"]
        self.assertIn(visit.id, [v["id"] for v in expected])

    def test_template_with_buttons_outside_the_window(self):
        with override_settings(WHATSAPP_TEMPLATE_WALK_IN="walk_in_request"):
            data = self.ask().json()
        message = client.OUTBOX[-1]
        self.assertEqual(message["type"], "template")
        payloads = [c["parameters"][0]["payload"] for c in message["template"]["components"] if c["type"] == "button"]
        self.assertEqual(payloads, [f"walkin_yes_{data['id']}", f"walkin_no_{data['id']}"])
        # Resident taps the template's quick-reply button.
        self.send(RESIDENT_A, {"type": "button", "button": {"payload": f"walkin_no_{data['id']}", "text": "Decline"}})
        self.assertEqual(WalkInRequest.objects.get().status, "declined")
        self.assertFalse(Visit.objects.exists())

    def test_no_whatsapp_means_guard_phones_and_records_answer(self):
        data = self.ask().json()  # no template and no open window
        self.assertFalse(data["whatsapp_sent"])
        self.assertEqual(data["resident_phone"], "0772111111")
        self.client.force_authenticate(self.guard)
        response = self.client.post(f"/gate/walk-ins/{data['id']}/decide", {"approve": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answered_via"], "phone")
        again = self.client.post(f"/gate/walk-ins/{data['id']}/decide", {"approve": False}, format="json")
        self.assertEqual(again.status_code, 409)

    def test_other_residents_cannot_answer(self):
        data = self.ask().json()
        self.tap(RESIDENT_B, f"walkin_yes_{data['id']}")
        self.assertEqual(WalkInRequest.objects.get().status, "pending")

    def test_resident_with_two_homes_can_answer_for_either(self):
        from home.models import Home
        from stand.models import Stand

        first = Home.objects.get(stand__stand_number=101)
        stand = Stand.objects.create(stand_number=103, stand_status=first.stand.stand_status, authorized_by=self.admin)
        Home.objects.create(owner=first.owner, stand=stand, address="103 Msasa Close", resident=self.resident_a,
                            home_status=first.home_status, authorized_by=self.admin)
        data = self.ask(stand=103).json()
        self.tap(RESIDENT_A, f"walkin_yes_{data['id']}")
        self.assertEqual(WalkInRequest.objects.get().status, "approved")

    def test_requests_expire(self):
        data = self.ask().json()
        WalkInRequest.objects.filter(pk=data["id"]).update(created_at=timezone.now() - datetime.timedelta(minutes=11))
        reply = self.tap(RESIDENT_A, f"walkin_yes_{data['id']}")
        self.assertIn("expired", self.body(reply))
        self.assertFalse(Visit.objects.exists())

    def test_unknown_stand(self):
        self.assertEqual(self.ask(stand=999).status_code, 400)

    def test_residents_cannot_use_the_gate_endpoints(self):
        self.assertEqual(self.client.post("/gate/walk-ins", {}, format="json").status_code, 401)


class RepairTests(BotCase):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        client.DRY_RUN_MEDIA.clear()

    def report(self):
        self.tap(RESIDENT_A, "repair")
        self.tap(RESIDENT_A, f"cat_{self.drainage.id}")
        reply = self.text(RESIDENT_A, "Burst pipe by the gate")
        self.assertIn("send a photo", self.body(reply))
        return Complain.objects.get()

    def image(self, media_id, mime="image/jpeg"):
        return self.send(RESIDENT_A, {"type": "image", "image": {"id": media_id, "mime_type": mime}})

    def test_photos_are_saved_with_the_report(self):
        complaint = self.report()
        client.DRY_RUN_MEDIA["m1"] = (b"\xff\xd8\xff fake jpeg", "image/jpeg")
        reply = self.image("m1")
        self.assertIn("1 of 3", self.body(reply))
        photo = ComplaintPhoto.objects.get()
        self.assertEqual(photo.complaint, complaint)
        self.assertEqual(photo.image.read(), b"\xff\xd8\xff fake jpeg")

        self.client.force_authenticate(self.admin)
        listing = self.client.get(f"/complain/{complaint.id}/photos").json()
        self.assertEqual(len(listing), 1)
        image = self.client.get(f"/{listing[0]['url']}")
        self.assertEqual(image["Content-Type"], "image/jpeg")
        self.assertEqual(b"".join(image.streaming_content), b"\xff\xd8\xff fake jpeg")
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/{listing[0]['url']}").status_code, 401)

        reply = self.tap(RESIDENT_A, "repair_done")
        self.assertEqual(WhatsAppSession.objects.get(wa_id=RESIDENT_A).state, "menu")

    def test_non_images_and_failed_downloads_are_refused(self):
        self.report()
        client.DRY_RUN_MEDIA["pdf"] = (b"%PDF", "application/pdf")
        self.assertIn("couldn't save", self.body(self.image("pdf")))
        self.assertIn("couldn't save", self.body(self.image("missing")))
        self.assertFalse(ComplaintPhoto.objects.exists())

    def test_photo_outside_a_report(self):
        self.image("x")
        self.assertIn("only take photos", self.body(client.OUTBOX[-2]))

    def test_resident_told_when_status_changes(self):
        complaint = self.report()
        in_progress = ComplaintStatus.objects.create(name="In progress")
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.put(f"/complain-update-status/{complaint.id}", {"compalint_status": in_progress.id}, format="json")
        self.assertEqual(response.status_code, 201)
        update = client.OUTBOX[-1]
        self.assertEqual(update["to"], RESIDENT_A)
        self.assertIn(f"*{complaint.complain_code}*", self.body(update))
        self.assertIn("In progress", self.body(update))

    def test_status_update_falls_back_to_sms(self):
        complaint = self.report()
        WhatsAppSession.objects.filter(wa_id=RESIDENT_A).update(last_inbound_at=timezone.now() - datetime.timedelta(days=2))
        sms.OUTBOX.clear()
        complaint.compalint_status = ComplaintStatus.objects.create(name="Resolved")
        with self.captureOnCommitCallbacks(execute=True):
            complaint.save()
        self.assertIn("is now Resolved", sms.OUTBOX[-1]["message"])

    def test_my_repairs(self):
        complaint = self.report()
        self.tap(RESIDENT_A, "repair_done")
        self.tap(RESIDENT_A, "repairs")
        self.assertIn(complaint.complain_code, self.body(client.OUTBOX[-2]))
        self.assertIn("Pending", self.body(client.OUTBOX[-2]))
