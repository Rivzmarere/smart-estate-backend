import datetime
from decimal import Decimal
from io import StringIO
from unittest import mock
from urllib.parse import urlencode

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from home.models import Home
from sms import sender as sms
from visit.tests import EstateFixture
from whatsapp import client
from whatsapp.tests import RESIDENT_A, BotCase

from . import paynow
from .accounts import account, allocate
from .models import ExchangeRate, Invoice, Payment

USD_KEY = "usd-test-key"
ZWG_KEY = "zwg-test-key"
PAYNOW = dict(
    PAYNOW_DRY_RUN=True,
    PAYNOW_USD_INTEGRATION_ID="1001",
    PAYNOW_USD_INTEGRATION_KEY=USD_KEY,
    PAYNOW_ZWG_INTEGRATION_ID="1002",
    PAYNOW_ZWG_INTEGRATION_KEY=ZWG_KEY,
    PAYNOW_AUTH_EMAIL="merchant@example.com",
    PUBLIC_API_URL="https://api.test",
)


def signed(pairs, key):
    return pairs + [("hash", paynow.sign(pairs, key))]


class LevyFixture(EstateFixture):
    def setUp(self):
        super().setUp()
        self.home_a = Home.objects.get(stand__stand_number=101)
        self.home_b = Home.objects.get(stand__stand_number=102)
        self.today = timezone.localdate()

    def invoice(self, home, amount, due, period=None, kind=Invoice.LEVY):
        return Invoice.objects.create(
            home=home, stand_number=home.stand.stand_number, address=home.address, kind=kind,
            period=period or due.replace(day=1), description="Levy", amount_usd=Decimal(amount), due_date=due,
        )

    def paid(self, home, amount_usd):
        payment = Payment.objects.create(home=home, amount=Decimal(amount_usd), amount_usd=Decimal(amount_usd), method=Payment.CASH, status=Payment.PENDING)
        payment.mark_paid()
        return payment


class AccountTests(LevyFixture):
    def test_payments_clear_the_oldest_invoice_first(self):
        last_month = self.today - datetime.timedelta(days=40)
        self.invoice(self.home_a, "30.00", last_month)
        current = self.invoice(self.home_a, "30.00", self.today + datetime.timedelta(days=10))
        self.paid(self.home_a, "40.00")
        acc = account(self.home_a)
        self.assertEqual(acc["balance"], Decimal("20.00"))
        self.assertEqual(acc["arrears"], Decimal("0.00"))  # the overdue one is fully paid
        states = [r["state"] for r in acc["invoices"]]
        self.assertEqual(states, ["paid", "part paid"])
        self.assertEqual(acc["invoices"][1]["invoice"], current)

    def test_arrears_count_only_overdue_amounts(self):
        self.invoice(self.home_a, "30.00", self.today - datetime.timedelta(days=40))
        self.invoice(self.home_a, "30.00", self.today - datetime.timedelta(days=5), period=self.today.replace(day=1) - datetime.timedelta(days=1))
        self.invoice(self.home_a, "30.00", self.today + datetime.timedelta(days=20), period=self.today.replace(day=1) + datetime.timedelta(days=32))
        self.paid(self.home_a, "10.00")
        acc = account(self.home_a)
        self.assertEqual(acc["balance"], Decimal("80.00"))
        self.assertEqual(acc["arrears"], Decimal("50.00"))

    def test_overpayment_is_credit(self):
        invoice = self.invoice(self.home_a, "30.00", self.today)
        rows, arrears, credit = allocate([invoice], Decimal("45.00"), self.today)
        self.assertEqual(credit, Decimal("15.00"))
        self.assertEqual(rows[0]["state"], "paid")

    def test_void_invoices_do_not_count(self):
        invoice = self.invoice(self.home_a, "30.00", self.today)
        invoice.void = True
        invoice.save()
        self.assertEqual(account(self.home_a)["balance"], Decimal("0.00"))


class AdminApiTests(LevyFixture):
    def test_only_admins_can_see_levies(self):
        self.assertEqual(self.client.get("/levies/accounts").status_code, 401)
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get("/levies/accounts").status_code, 403)

    def test_generate_bills_each_home_once(self):
        self.client.force_authenticate(self.admin)
        body = {"period": "2026-12", "amount_usd": "45.00", "due_date": "2026-12-07"}
        preview = self.client.post("/levies/invoices/generate", {**body, "preview": True}, format="json")
        self.assertEqual(preview.json()["to_create"], 2)
        self.assertEqual(Invoice.objects.count(), 0)

        created = self.client.post("/levies/invoices/generate", body, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["created"], 2)
        again = self.client.post("/levies/invoices/generate", body, format="json")
        self.assertEqual(again.json()["created"], 0)
        self.assertEqual(Invoice.objects.count(), 2)
        invoice = Invoice.objects.get(home=self.home_a)
        self.assertEqual(invoice.description, "Levy for December 2026")
        self.assertTrue(invoice.number.startswith("INV"))

    def test_due_date_before_the_month_is_refused(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/levies/invoices/generate", {"period": "2026-12", "amount_usd": "45", "due_date": "2026-11-20"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_record_zig_cash_payment_converts_at_todays_rate(self):
        ExchangeRate.objects.create(effective_from=self.today, zig_per_usd=Decimal("26.80"))
        self.invoice(self.home_a, "45.00", self.today)
        self.client.force_authenticate(self.admin)
        response = self.client.post("/levies/payments", {"home": self.home_a.id, "currency": "ZWG", "amount": "536.00", "method": "cash"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        payment = Payment.objects.get()
        self.assertEqual(payment.amount_usd, Decimal("20.00"))
        self.assertEqual(payment.exchange_rate, Decimal("26.80"))
        self.assertEqual(payment.status, Payment.PAID)
        self.assertTrue(payment.receipt_number.startswith("R"))
        self.assertEqual(account(self.home_a)["balance"], Decimal("25.00"))
        self.assertIn(payment.receipt_number, sms.OUTBOX[-1]["message"])  # receipt by SMS (WhatsApp is off)

    def test_zig_payment_needs_a_rate(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/levies/payments", {"home": self.home_a.id, "currency": "ZWG", "amount": "100", "method": "cash"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("exchange_rate", response.json())

    def test_statement_and_accounts(self):
        self.invoice(self.home_a, "45.00", self.today - datetime.timedelta(days=3))
        self.paid(self.home_a, "15.00")
        self.client.force_authenticate(self.admin)
        rows = {r["stand_number"]: r for r in self.client.get("/levies/accounts").json()["accounts"]}
        self.assertEqual(Decimal(rows[101]["arrears"]), Decimal("30.00"))
        self.assertEqual(Decimal(rows[102]["balance"]), Decimal("0"))
        statement = self.client.get(f"/levies/accounts/{self.home_a.id}").json()
        self.assertEqual([e["kind"] for e in statement["statement"]], ["invoice", "payment"])
        self.assertEqual(Decimal(statement["statement"][-1]["balance"]), Decimal("30.00"))

    def test_rate_for_the_same_day_is_corrected_not_duplicated(self):
        self.client.force_authenticate(self.admin)
        first = self.client.post("/levies/rates", {"effective_from": "2026-11-15", "zig_per_usd": "2.68"}, format="json")
        self.assertEqual(first.status_code, 201)
        fixed = self.client.post("/levies/rates", {"effective_from": "2026-11-15", "zig_per_usd": "26.80"}, format="json")
        self.assertEqual(fixed.status_code, 200)
        self.assertEqual(ExchangeRate.objects.get().zig_per_usd, Decimal("26.80"))

    def test_void_invoice(self):
        invoice = self.invoice(self.home_a, "45.00", self.today)
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/levies/invoices/{invoice.id}/void", {"reason": "Billed twice"}, format="json")
        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertTrue(invoice.void)


@override_settings(**PAYNOW)
class PaynowTests(LevyFixture):
    def setUp(self):
        super().setUp()
        paynow.OUTBOX.clear()
        sms.OUTBOX.clear()

    def pending(self, amount="45.00", currency=Payment.USD):
        payment = Payment.objects.create(
            home=self.home_a, amount=Decimal(amount), amount_usd=Decimal(amount), currency=currency,
            method=Payment.ECOCASH, status=Payment.PENDING, phone="0772111111",
        )
        paynow.start_mobile_payment(payment, "Levy")
        return payment

    def result(self, payment, status="Paid", amount=None, key=USD_KEY):
        pairs = signed([("reference", payment.reference_for_paynow), ("paynowreference", "987654"),
                        ("amount", amount or f"{payment.amount:.2f}"), ("status", status),
                        ("pollurl", payment.poll_url)], key)
        return self.client.post(f"/paynow/result/{payment.id}", data=urlencode(pairs), content_type="application/x-www-form-urlencoded")

    def test_request_is_signed_in_field_order(self):
        payment = self.pending()
        sent = paynow.OUTBOX[-1]
        self.assertEqual(sent["id"], "1001")
        self.assertEqual(sent["method"], "ecocash")
        self.assertEqual(sent["amount"], "45.00")
        self.assertEqual(sent["resulturl"], f"https://api.test/paynow/result/{payment.id}")
        self.assertTrue(paynow.verify(list(sent.items()), USD_KEY))
        self.assertFalse(paynow.verify(list(sent.items()), "wrong-key"))

    def test_paid_result_marks_payment_and_sends_receipt(self):
        payment = self.pending()
        self.assertEqual(self.result(payment).status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.PAID)
        self.assertEqual(payment.paynow_reference, "987654")
        self.assertEqual(len(sms.OUTBOX), 1)
        # Paynow repeats results; the second one changes nothing.
        self.assertEqual(self.result(payment).status_code, 200)
        self.assertEqual(len(sms.OUTBOX), 1)

    def test_forged_result_is_rejected(self):
        payment = self.pending()
        self.assertEqual(self.result(payment, key="attacker").status_code, 400)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.PENDING)

    def test_wrong_amount_is_not_accepted(self):
        payment = self.pending()
        self.result(payment, amount="1.00")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.PENDING)
        self.assertIn("mismatch", payment.failure_reason)

    def test_cancelled_by_payer(self):
        payment = self.pending()
        self.result(payment, status="Cancelled")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.CANCELLED)

    def test_zig_uses_the_zig_integration(self):
        payment = self.pending(amount="1206.00", currency=Payment.ZWG)
        self.assertEqual(paynow.OUTBOX[-1]["id"], "1002")
        self.assertEqual(self.result(payment, key=USD_KEY).status_code, 400)
        self.assertEqual(self.result(payment, key=ZWG_KEY).status_code, 200)

    def test_network_from_number(self):
        self.assertEqual(paynow.method_for_phone("0772111111"), "ecocash")
        self.assertEqual(paynow.method_for_phone("+263 78 211 1111"), "ecocash")
        self.assertEqual(paynow.method_for_phone("0712111111"), "onemoney")
        self.assertIsNone(paynow.method_for_phone("0732111111"))

    def test_poll_command_gives_up_after_a_day(self):
        payment = self.pending()
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - datetime.timedelta(days=2))
        call_command("paynow_poll", stdout=StringIO(), skip_checks=False)  # like the server runs it
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.FAILED)


@override_settings(**PAYNOW)
class LevyBotTests(BotCase):
    def setUp(self):
        super().setUp()
        paynow.OUTBOX.clear()
        self.home_a = Home.objects.get(stand__stand_number=101)
        today = timezone.localdate()
        Invoice.objects.create(
            home=self.home_a, stand_number=101, address=self.home_a.address, period=today.replace(day=1),
            description="Levy", amount_usd=Decimal("45.00"), due_date=today - datetime.timedelta(days=1),
        )

    def test_pay_full_balance_with_ecocash_and_get_receipt(self):
        reply = self.tap(RESIDENT_A, "levy")
        self.assertIn("USD 45.00", self.body(reply))
        self.assertIn("Overdue", self.body(reply))
        self.assertEqual(self.choice_ids(reply), ["levy_all", "levy_other", "levy_back"])
        reply = self.tap(RESIDENT_A, "levy_all")  # no ZiG rate set, so straight to the phone
        self.assertEqual(self.choice_ids(reply), ["payphone_self", "payphone_other"])
        reply = self.tap(RESIDENT_A, "payphone_self")
        self.assertIn("payment request for *USD 45.00* to 0772111111", self.body(reply))
        self.assertEqual(paynow.OUTBOX[-1]["phone"], "0772111111")

        payment = Payment.objects.get()
        self.assertEqual(payment.channel, Payment.WHATSAPP)
        pairs = signed([("reference", payment.reference_for_paynow), ("paynowreference", "1"), ("amount", "45.00"), ("status", "Paid")], USD_KEY)
        self.client.post(f"/paynow/result/{payment.id}", data=urlencode(pairs), content_type="application/x-www-form-urlencoded")
        receipt = self.body(client.OUTBOX[-1])
        payment.refresh_from_db()
        self.assertIn(payment.receipt_number, receipt)
        self.assertIn("fully paid", receipt)
        self.assertEqual(client.OUTBOX[-1]["to"], RESIDENT_A)

    def test_choose_zig_and_another_amount_and_number(self):
        ExchangeRate.objects.create(effective_from=timezone.localdate(), zig_per_usd=Decimal("26.80"))
        reply = self.tap(RESIDENT_A, "levy")
        self.assertIn("ZiG 1,206.00", self.body(reply))
        self.tap(RESIDENT_A, "levy_other")
        reply = self.text(RESIDENT_A, "$20")
        self.assertEqual(self.choice_ids(reply), ["cur_USD", "cur_ZWG"])
        self.tap(RESIDENT_A, "cur_ZWG")
        self.tap(RESIDENT_A, "payphone_other")
        reply = self.text(RESIDENT_A, "0732 000 000")
        self.assertIn("isn't an EcoCash", self.body(reply))
        reply = self.text(RESIDENT_A, "0712 345 678")
        self.assertIn("ZiG 536.00", self.body(reply))
        self.assertIn("OneMoney", self.body(reply))
        payment = Payment.objects.get()
        self.assertEqual((payment.currency, payment.amount, payment.amount_usd), ("ZWG", Decimal("536.00"), Decimal("20.00")))
        self.assertEqual(paynow.OUTBOX[-1]["id"], "1002")

    def test_one_prompt_at_a_time(self):
        self.tap(RESIDENT_A, "levy")
        self.tap(RESIDENT_A, "levy_all")
        self.tap(RESIDENT_A, "payphone_self")
        self.tap(RESIDENT_A, "levy")
        self.assertIn("waiting on 0772111111", self.body(client.OUTBOX[-2]))
        self.assertEqual(Payment.objects.count(), 1)

    def test_up_to_date(self):
        Payment.objects.create(home=self.home_a, amount=Decimal("45"), amount_usd=Decimal("45"), method="cash", status="paid")
        reply = self.tap(RESIDENT_A, "levy")
        self.assertIn("up to date", self.body(reply))

    @override_settings(PAYNOW_USD_INTEGRATION_ID="", PAYNOW_ZWG_INTEGRATION_ID="")
    def test_without_paynow_shows_balance_only(self):
        self.tap(RESIDENT_A, "levy")
        self.assertIn("contact the estate office", self.body(client.OUTBOX[-2]))

    def test_paynow_refusal_is_explained(self):
        with mock.patch("levy.paynow.start_mobile_payment", side_effect=paynow.PaynowError("Invalid phone.")):
            self.tap(RESIDENT_A, "levy")
            self.tap(RESIDENT_A, "levy_all")
            self.tap(RESIDENT_A, "payphone_self")
        self.assertIn("Invalid phone.", self.body(client.OUTBOX[-2]))
        self.assertEqual(Payment.objects.get().status, Payment.FAILED)
