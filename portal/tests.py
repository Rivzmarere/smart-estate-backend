import datetime
import shutil
import tempfile
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone

from assist.models import Conversation, EmergencyAlert
from complaint.models import Complain, ComplaintPhoto
from estates.models import Estate
from gatepass.models import WalkInRequest
from home.models import Home
from levy.models import Invoice, Payment
from levy.tests import PAYNOW
from parameters.models.models_complaint_category import ComplaintCategory
from parameters.models.models_complaint_status import ComplaintStatus
from sms import sender as sms
from visit.models import Visit
from visit.tests import EstateFixture

from . import auth
from .models import HouseholdMember, HouseholdRequest, LoginCode

RESIDENT = "0772111111"  # resident of stand 101
OWNER = "0771000001"  # owns both homes
OTHER = "0773222222"  # resident of stand 102


class PortalCase(EstateFixture):
    def setUp(self):
        super().setUp()
        sms.OUTBOX.clear()
        self.estate = Estate.objects.get(slug="main")
        self.home = Home.objects.get(stand__stand_number=101)
        self.other_home = Home.objects.get(stand__stand_number=102)
        self.client.defaults["HTTP_X_ESTATE"] = "main"

    def sign_in(self, phone):
        principal_phone = sms.zimbabwe_mobile(phone)
        token = auth.make_token(self.estate, principal_phone)
        self.client.credentials(HTTP_AUTHORIZATION=f"Resident {token}")

    def url(self, path, home=None):
        return f"/resident/homes/{(home or self.home).id}{path}"


class SignInTests(PortalCase):
    def test_code_by_sms_then_token(self):
        response = self.client.post("/resident/login/code", {"phone": "0772 111 111"}, format="json")
        self.assertEqual(response.status_code, 200)
        message = sms.OUTBOX[-1]["message"]
        code = message.split("code is ")[1][:6]
        self.assertTrue(LoginCode.objects.get().code_hash)
        self.assertNotIn(code, LoginCode.objects.get().code_hash)  # only a hash is kept
        verified = self.client.post("/resident/login/verify", {"phone": "0772111111", "code": code}, format="json")
        self.assertEqual(verified.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Resident {verified.json()['token']}")
        me = self.client.get("/resident/me").json()
        self.assertEqual([h["stand_number"] for h in me["homes"]], [101])
        self.assertEqual(me["homes"][0]["role"], "resident")
        # A code works once.
        again = self.client.post("/resident/login/verify", {"phone": "0772111111", "code": code}, format="json")
        self.assertEqual(again.status_code, 400)

    def test_unknown_numbers_get_the_same_answer_and_no_sms(self):
        response = self.client.post("/resident/login/code", {"phone": "0779999999"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sms.OUTBOX, [])

    def test_wrong_codes_lock_the_code(self):
        self.client.post("/resident/login/code", {"phone": RESIDENT}, format="json")
        code = sms.OUTBOX[-1]["message"].split("code is ")[1][:6]
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.client.post("/resident/login/verify", {"phone": RESIDENT, "code": wrong}, format="json")
        self.assertEqual(self.client.post("/resident/login/verify", {"phone": RESIDENT, "code": code}, format="json").status_code, 400)

    def test_resident_tokens_never_open_staff_endpoints(self):
        self.sign_in(RESIDENT)
        for url in ["/home", "/visit", "/levies/accounts", "/inbox", "/gate/expected", "/users-all"]:
            self.assertIn(self.client.get(url).status_code, (401, 403), url)

    def test_staff_tokens_do_not_open_the_portal(self):
        self.client.force_authenticate(self.admin)
        self.assertIn(self.client.get("/resident/me").status_code, (401, 403))

    def test_cannot_reach_another_home(self):
        self.sign_in(RESIDENT)
        self.assertEqual(self.client.get(self.url("", self.other_home)).status_code, 404)
        self.assertEqual(self.client.get(self.url("/visitors", self.other_home)).status_code, 404)

    def test_owner_sees_both_homes(self):
        self.sign_in(OWNER)
        homes = self.client.get("/resident/me").json()["homes"]
        self.assertEqual({h["stand_number"] for h in homes}, {101, 102})
        self.assertTrue(all(h["role"] == "owner" and h["can"]["tenancy"] for h in homes))


class VisitorAndRepairTests(PortalCase):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        ComplaintStatus.objects.create(name="Pending")
        self.category = ComplaintCategory.objects.create(name="Water")

    def test_book_list_and_cancel(self):
        self.sign_in(RESIDENT)
        booked = self.client.post(self.url("/visitors"), {"visitor_name": "Chipo  Banda", "visitor_phone_number": "0774 555 666",
                                                          "transport_type": self.transport.id}, format="json")
        self.assertEqual(booked.status_code, 201, booked.content)
        self.assertTrue(booked.json()["sms_sent"])
        visit = Visit.objects.get()
        self.assertEqual((visit.stand_number, visit.visitor_name, visit.resident_phone_number), (101, "Chipo Banda", "0772111111"))
        self.assertEqual(self.client.get(self.url("/visitors")).json()[0]["state"], "expected")
        self.assertEqual(self.client.post(self.url(f"/visitors/{visit.id}/cancel")).json()["state"], "cancelled")

    def test_answer_a_walk_in(self):
        walk_in = WalkInRequest.objects.create(home=self.home, stand_number=101, address=self.home.address, resident_phone="0772111111",
                                               visitor_name="Tatenda Shumba", requested_by=self.guard)
        self.sign_in(RESIDENT)
        self.assertEqual(self.client.get(self.url("/walk-ins")).json()[0]["status"], "pending")
        answer = self.client.post(self.url(f"/walk-ins/{walk_in.id}/answer"), {"approve": True}, format="json").json()
        self.assertEqual(answer["status"], "approved")
        self.assertTrue(answer["visit_code"])

    def test_report_repair_with_photo(self):
        self.sign_in(RESIDENT)
        from django.core.files.uploadedfile import SimpleUploadedFile

        photo = SimpleUploadedFile("leak.jpg", b"\xff\xd8\xff\xe0 fake jpeg body", content_type="image/jpeg")
        response = self.client.post(self.url("/repairs"), {"category": self.category.id, "description": "Pipe leaking by the gate", "photos": [photo]}, format="multipart")
        self.assertEqual(response.status_code, 201, response.content)
        complaint = Complain.objects.get()
        self.assertEqual(ComplaintPhoto.objects.get().complaint, complaint)
        self.assertEqual(self.client.get(self.url("/repairs")).json()[0]["photos"], 1)

    def test_fake_photo_is_refused(self):
        self.sign_in(RESIDENT)
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile("x.jpg", b"<html>not an image</html>", content_type="image/jpeg")
        response = self.client.post(self.url("/repairs"), {"category": self.category.id, "description": "Something broken", "photos": [fake]}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Complain.objects.exists())

    def test_chat_and_emergency(self):
        self.sign_in(RESIDENT)
        self.client.post(self.url("/chat"), {"text": "When is the next meeting?"}, format="json")
        convo = Conversation.objects.get()
        self.assertEqual((convo.channel, convo.unread), ("portal", 1))
        self.client.force_authenticate(self.admin)
        sent = self.client.post(f"/inbox/{convo.id}/reply", {"text": "Saturday at 10."}, format="json").json()
        self.assertTrue(sent["delivered"])
        self.client.force_authenticate(None)
        self.sign_in(RESIDENT)
        messages = self.client.get(self.url("/chat")).json()["messages"]
        self.assertEqual([m["from"] for m in messages], ["me", "office"])
        alert = self.client.post(self.url("/emergency"), {"kind": "medical", "details": "Collapsed in the garden"}, format="json")
        self.assertEqual(alert.status_code, 201)
        self.assertEqual(EmergencyAlert.objects.get().kind, "medical")


@override_settings(**PAYNOW)
class LevyTests(PortalCase):
    def setUp(self):
        super().setUp()
        Invoice.objects.create(home=self.home, stand_number=101, address=self.home.address, period=datetime.date(2026, 11, 1),
                               description="Levy", amount_usd=Decimal("45.00"), due_date=timezone.localdate() - datetime.timedelta(days=1))

    def test_balance_and_pay(self):
        self.sign_in(RESIDENT)
        levy = self.client.get(self.url("/levy")).json()
        self.assertEqual((Decimal(levy["balance"]), Decimal(levy["arrears"]), levy["can_pay"]), (Decimal("45.00"), Decimal("45.00"), True))
        paid = self.client.post(self.url("/levy/pay"), {"amount_usd": "45.00", "currency": "USD", "phone": "0772 111 111"}, format="json")
        self.assertEqual(paid.status_code, 201, paid.content)
        self.assertEqual(Payment.objects.get().channel, "whatsapp")  # mobile-money flow, receipt to the phone
        busy = self.client.post(self.url("/levy/pay"), {"amount_usd": "10", "currency": "USD", "phone": "0772111111"}, format="json")
        self.assertEqual(busy.status_code, 409)

    def test_household_members_cannot_see_the_levy(self):
        HouseholdMember.objects.create(home=self.home, name="Nyasha", phone="+263775000111")
        self.sign_in("0775000111")
        self.assertEqual(self.client.get(self.url("/levy")).status_code, 404)
        self.assertEqual(self.client.get(self.url("/visitors")).status_code, 200)


class HouseholdTests(PortalCase):
    def test_resident_adds_family_after_office_approval(self):
        self.sign_in(RESIDENT)
        sent = self.client.post(self.url("/household/requests"), {"kind": "add_member", "name": "Nyasha", "surname": "Ncube",
                                                                    "phone": "0775 000 111", "relationship": "family"}, format="json")
        self.assertEqual(sent.status_code, 201, sent.content)
        self.assertEqual(sent.json()["status"], "pending")
        self.assertFalse(HouseholdMember.objects.exists())

        self.client.credentials()
        self.client.force_authenticate(self.admin)
        pending = self.client.get("/household/requests").json()
        self.assertEqual(pending[0]["summary"], "Add Nyasha Ncube (0775000111) as family")
        self.client.post(f"/household/requests/{pending[0]['id']}/decide", {"approve": True}, format="json")
        member = HouseholdMember.objects.get()
        self.assertEqual(member.phone, "+263775000111")
        self.assertIn("approved", sms.OUTBOX[-1]["message"])

        # The new member can now sign in and book, but not change the household.
        self.client.force_authenticate(None)
        self.sign_in("0775000111")
        self.assertEqual(self.client.get("/resident/me").json()["homes"][0]["role"], "member")
        refused = self.client.post(self.url("/household/requests"), {"kind": "remove_member", "member_id": member.id}, format="json")
        self.assertEqual(refused.status_code, 400)

    def test_removing_a_member_is_immediate(self):
        member = HouseholdMember.objects.create(home=self.home, name="Gift", phone="+263776000222", relationship="worker")
        self.sign_in(RESIDENT)
        response = self.client.post(self.url("/household/requests"), {"kind": "remove_member", "member_id": member.id}, format="json")
        self.assertEqual(response.json()["status"], "approved")
        member.refresh_from_db()
        self.assertFalse(member.active)

    def test_only_the_owner_changes_the_tenant(self):
        self.sign_in(RESIDENT)
        refused = self.client.post(self.url("/household/requests"), {"kind": "resident_leaves"}, format="json")
        self.assertEqual(refused.status_code, 400)

        Estate.objects.filter(pk=self.estate.pk).update(household_approval=False)
        self.sign_in(OWNER)
        moved = self.client.post(self.url("/household/requests"), {"kind": "new_resident", "name": "Tapiwa", "surname": "Gumbo",
                                                                     "phone": "0778 123 456", "move_in": "2026-12-01"}, format="json")
        self.assertEqual(moved.json()["status"], "approved")  # no approval needed for this estate
        self.home.refresh_from_db()
        self.assertEqual((self.home.resident.name, self.home.resident.phone_number1), ("Tapiwa", "0778123456"))
        # The old tenant lost access; the new one has it.
        self.sign_in(RESIDENT)
        self.assertEqual(self.client.get("/resident/me").json()["homes"], [])
        self.sign_in("0778123456")
        self.assertEqual(self.client.get("/resident/me").json()["homes"][0]["stand_number"], 101)

    def test_office_can_reject(self):
        self.sign_in(OWNER)
        sent = self.client.post(self.url("/household/requests"), {"kind": "resident_leaves"}, format="json").json()
        self.client.credentials()
        self.client.force_authenticate(self.admin)
        self.client.post(f"/household/requests/{sent['id']}/decide", {"approve": False, "note": "Levy arrears first"}, format="json")
        self.assertEqual(HouseholdRequest.objects.get().status, "rejected")
        self.home.refresh_from_db()
        self.assertIsNotNone(self.home.resident)
        self.assertIn("Levy arrears first", sms.OUTBOX[-1]["message"])


class SharedAccessTests(PortalCase):
    def test_members_can_use_the_public_form_and_whatsapp(self):
        HouseholdMember.objects.create(home=self.home, name="Nyasha", phone="+263775000111")
        booking = self.booking(101, "0775000111")
        self.assertEqual(self.client.post("/visit", booking, format="json").status_code, 201)
        from whatsapp.bot import find_home

        self.assertEqual(find_home("263775000111"), self.home)

    def test_limited_members_cannot_book(self):
        HouseholdMember.objects.create(home=self.home, name="Gift", phone="+263776000222", can_book_visitors=False)
        self.sign_in("0776000222")
        self.assertEqual(self.client.post(self.url("/visitors"), {"visitor_name": "X Y", "transport_type": self.transport.id}, format="json").status_code, 404)
