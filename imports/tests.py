import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from rest_framework.test import APITestCase

from authentication.models import User
from estates.context import use_estate
from estates.models import Estate
from home.models import Home
from levy.accounts import account
from levy.models import Invoice, Payment
from owner.models import Owner
from rentals import services as rentals
from rentals.models import Lease
from resident.models import Resident
from smartEstateBackend.permissions import ROLE_ADMIN, ROLE_GUARD
from stand.models import Stand

from .models import ImportBatch

HOMES_HEADER = "Stand number,Address,Owner first name,Owner surname,Owner mobile,Owner lives here,Resident first name,Resident surname,Resident mobile,Levy owed (USD)\n"


def csv_file(text, name="homes.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def xlsx_file(rows, name="data.xlsx"):
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return SimpleUploadedFile(name, out.getvalue())


class ImportTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.estate = Estate.objects.create(name="Import Park", slug="import-park")
        cls.rental = Estate.objects.create(name="Import Rentals", slug="import-rentals", kind=Estate.RENTAL)
        cls.admin = User.objects.create_user(username="imp-admin", password="S3cure-pass!", role=ROLE_ADMIN, estate=cls.estate)
        cls.guard = User.objects.create_user(username="imp-guard", password="S3cure-pass!", role=ROLE_GUARD, estate=cls.estate)
        cls.landlord = User.objects.create_user(username="imp-landlord", password="S3cure-pass!", role=ROLE_ADMIN, estate=cls.rental)

    def post(self, path, kind, upload, user=None):
        self.client.force_authenticate(user or self.admin)
        return self.client.post(path, {"kind": kind, "file": upload}, format="multipart")

    def homes_csv(self):
        return csv_file(
            HOMES_HEADER
            + "101,101 Acacia Drive,Tendai,Ncube,0772 123 456,Yes,,,,45\n"
            + "102,102 Acacia Drive,Precious,Chiwenga,+263 712 345 678,No,Farai,Dube,0773222333,\n"
            + "103,103 Acacia Drive,Precious,Chiwenga,263712345678,No,,,,-20\n"
            + ",,,,,,,,,\n"
        )

    # ---------------------------------------------------------------- gated estates

    def test_check_saves_nothing(self):
        response = self.post("/imports/check", "homes", self.homes_csv())
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"], data)
        self.assertEqual(data["rows"], 3)
        self.assertEqual(data["counts"]["homes"], 3)
        self.assertEqual(data["counts"]["owners"], 2)
        self.assertEqual(len(data["preview"]), 3)
        with use_estate(self.estate):
            self.assertEqual(Home.objects.count(), 0)
            self.assertEqual(Owner.objects.count(), 0)
        self.assertFalse(ImportBatch.all_estates.exists())

    def test_homes_import(self):
        response = self.post("/imports/run", "homes", self.homes_csv())
        self.assertEqual(response.status_code, 201, response.content)
        with use_estate(self.estate):
            self.assertEqual(Home.objects.count(), 3)
            self.assertEqual(Owner.objects.count(), 2, "an owner with two homes is added once")
            first = Home.objects.get(stand__stand_number=101)
            self.assertEqual(first.resident.name, "Tendai")
            self.assertEqual(first.home_status.name, "Owner occupied")
            second = Home.objects.get(stand__stand_number=102)
            self.assertEqual(second.owner.phone_number1, "0712345678")
            self.assertEqual(second.resident.phone_number1, "0773222333")
            self.assertEqual(second.home_status.name, "Rented")
            third = Home.objects.get(stand__stand_number=103)
            self.assertIsNone(third.resident)
            self.assertEqual(third.home_status.name, "Vacant")

            owed = account(first)
            self.assertEqual(owed["balance"], Decimal("45.00"))
            self.assertEqual(owed["arrears"], Decimal("45.00"), "money owed before Smart Estate is overdue at once")
            credit = account(third)
            self.assertEqual(credit["balance"], Decimal("-20.00"))
            self.assertEqual(Payment.objects.get().method, Payment.OPENING)
            # A credit carried over is not money collected this month.
            month = rentals.collected_between(rentals.month_start(timezone.localdate()), timezone.localdate())
            self.assertEqual(sum(month.values(), Decimal(0)), 0)
        batch = ImportBatch.all_estates.get()
        self.assertEqual(batch.estate, self.estate)
        self.assertEqual(batch.summary["homes"], 3)

    def test_problems_stop_the_whole_import(self):
        upload = csv_file(
            HOMES_HEADER
            + "101,101 Acacia Drive,Tendai,Ncube,0772123456,Yes,,,,\n"
            + "101,Another,Rudo,Moyo,0772000111,Yes,,,,\n"
            + "105,105 Acacia,Rudo,Moyo,12,Yes,,,,\n"
            + "106,106 Acacia,Rudo,,0772000999,Yes,,,,\n"
            + "107,107 Acacia,Chipo,Banda,0772123456,Yes,,,,abc\n"
        )
        response = self.post("/imports/run", "homes", upload)
        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        rows = {e["row"] for e in errors}
        self.assertEqual(rows, {3, 4, 5, 6})
        self.assertTrue(any("also on row 2" in e["message"] for e in errors))
        self.assertTrue(any(e["column"] == "Owner mobile" for e in errors))
        self.assertTrue(any(e["column"] == "Owner surname" and "empty" in e["message"] for e in errors))
        with use_estate(self.estate):
            self.assertEqual(Home.objects.count(), 0, "nothing is saved when any row is wrong")

    def test_same_mobile_different_name_is_a_problem(self):
        upload = csv_file(HOMES_HEADER + "101,1 A,Tendai,Ncube,0772123456,Yes,,,,\n" + "102,2 A,Chipo,Banda,0772123456,Yes,,,,\n")
        errors = self.post("/imports/check", "homes", upload).json()["errors"]
        self.assertEqual(len(errors), 1)
        self.assertIn("already belongs to Tendai Ncube", errors[0]["message"])

    def test_stand_already_in_the_system(self):
        self.post("/imports/run", "homes", self.homes_csv())
        errors = self.post("/imports/check", "homes", self.homes_csv()).json()["errors"]
        self.assertEqual(len(errors), 3)
        self.assertIn("already in the system", errors[0]["message"])

    def test_missing_columns_and_bad_files(self):
        response = self.post("/imports/check", "homes", csv_file("Stand number,Address\n1,x\n"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Owner first name", response.json()["detail"])
        response = self.post("/imports/check", "homes", csv_file("just,some,text\n1,2,3\n"))
        self.assertIn("No header row", response.json()["detail"])
        response = self.post("/imports/check", "homes", SimpleUploadedFile("old.xls", b"\xd0\xcf\x11\xe0junk"))
        self.assertIn(".xlsx", response.json()["detail"])

    def test_excel_with_title_rows_and_other_header_names(self):
        upload = xlsx_file([
            ["Acacia Park owners list 2025"],
            [],
            ["Stand No", "House address", "Owner Name", "Owner Last Name", "Owner Cell", "Owner Occupied", "Arrears", "Notes"],
            [101, "101 Acacia Drive", "Tendai", "Ncube", 772123456, "y", "$1,250.50", "pays late"],
            [102.0, "102 Acacia Drive", "Rudo", "Moyo", "0772 000 102", "Yes", "(30)", ""],
        ])
        data = self.post("/imports/run", "homes", upload).json()
        self.assertTrue(data["ok"], data)
        self.assertEqual(data["ignored_columns"], ["Notes"])
        with use_estate(self.estate):
            home = Home.objects.get(stand__stand_number=101)
            self.assertEqual(home.owner.phone_number1, "0772123456")
            self.assertEqual(account(home)["balance"], Decimal("1250.50"))
            self.assertEqual(account(Home.objects.get(stand__stand_number=102))["balance"], Decimal("-30.00"))

    def test_semicolon_csv(self):
        upload = csv_file("Stand number;Address;Owner first name;Owner surname;Owner mobile\n7;7 Msasa Close;Gift;Mpofu;0772000007\n")
        data = self.post("/imports/run", "homes", upload).json()
        self.assertTrue(data["ok"], data)

    def test_template_round_trip(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/imports/template?kind=homes&type=xlsx")
        self.assertEqual(response.status_code, 200)
        book = load_workbook(io.BytesIO(response.content))
        self.assertEqual(book.sheetnames, ["Homes", "Instructions"])
        sheet = book["Homes"]
        self.assertEqual(sheet["A1"].value, "Stand number *")
        sheet.append([101, "101 Acacia Drive", "Tendai", "Ncube", "0772123456", "", "", "Yes"])
        out = io.BytesIO()
        book.save(out)
        data = self.post("/imports/run", "homes", SimpleUploadedFile("filled.xlsx", out.getvalue())).json()
        self.assertTrue(data["ok"], data)
        self.assertEqual(data["counts"]["homes"], 1)
        csv_template = self.client.get("/imports/template?kind=homes&type=csv")
        self.assertTrue(csv_template.content.decode("utf-8-sig").startswith("Stand number,Address,"))

    def test_undo(self):
        batch = self.post("/imports/run", "homes", self.homes_csv()).json()["batch"]
        response = self.client.post(f"/imports/{batch}/undo")
        self.assertEqual(response.status_code, 200, response.content)
        with use_estate(self.estate):
            self.assertEqual(Home.objects.count(), 0)
            self.assertEqual(Owner.objects.count(), 0)
            self.assertEqual(Resident.objects.count(), 0)
            self.assertEqual(Stand.objects.count(), 0)
            self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(self.client.post(f"/imports/{batch}/undo").status_code, 400)

    def test_no_undo_once_used(self):
        batch = self.post("/imports/run", "homes", self.homes_csv()).json()["batch"]
        with use_estate(self.estate):
            home = Home.objects.get(stand__stand_number=101)
            Payment.objects.create(home=home, amount=10, amount_usd=10, method=Payment.CASH, status=Payment.PAID, paid_at=timezone.now())
        response = self.client.post(f"/imports/{batch}/undo")
        self.assertEqual(response.status_code, 400)
        self.assertIn("used since", response.json()["detail"])
        with use_estate(self.estate):
            self.assertEqual(Home.objects.count(), 3)

    def test_only_admins_and_the_right_imports(self):
        self.assertEqual(self.post("/imports/check", "homes", self.homes_csv(), user=self.guard).status_code, 403)
        self.assertEqual(self.post("/imports/check", "properties", self.homes_csv()).status_code, 400)
        self.client.force_authenticate(self.admin)
        kinds = [k["kind"] for k in self.client.get("/imports").json()["kinds"]]
        self.assertEqual(kinds, ["homes", "balances"])

    def test_another_estates_import_cannot_be_undone(self):
        batch = self.post("/imports/run", "homes", self.homes_csv()).json()["batch"]
        self.client.force_authenticate(self.landlord)
        self.assertEqual(self.client.post(f"/imports/{batch}/undo").status_code, 404)

    # ---------------------------------------------------------------- rentals

    def test_properties_import(self):
        today = timezone.localdate()
        start = rentals.month_start(today).replace(year=today.year - 1)
        upload = xlsx_file([
            ["Reference", "Address", "Owner first name", "Owner surname", "Owner mobile", "Tenant first name", "Tenant surname",
             "Tenant mobile", "Monthly rent (USD)", "Lease start", "Lease end", "Rent due day", "Deposit (USD)", "Deposit paid (USD)", "Rent owed (USD)"],
            [None, "Flat 3, Baines Court", "Tawanda", "Makoni", "0772900100", "Rudo", "Moyo", "0771000201", 450, start, None, 5, 450, None, 900],
            [None, "14 Quorn Avenue", "Tawanda", "Makoni", "0772900100", "Tendai", "Ncube", "", "900", start.isoformat(), None, None, None, None, None],
            [None, "Unit 3, Kaguvi Street", "Precious", "Chiwenga", "0712345678"],
        ])
        response = self.post("/imports/run", "properties", upload, user=self.landlord)
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["counts"]["properties"], 3)
        self.assertEqual(data["counts"]["leases"], 2)
        self.assertEqual(data["warning_count"], 1, "a tenant without a mobile")
        with use_estate(self.rental):
            self.assertEqual(sorted(Stand.objects.values_list("stand_number", flat=True)), [1, 2, 3])
            lease = Lease.objects.get(tenant__name="Rudo")
            self.assertEqual(lease.due_day, 5)
            self.assertEqual(lease.deposit_paid_usd, Decimal("450.00"))
            self.assertEqual(lease.home.resident, lease.tenant)
            acc = rentals.lease_account(lease)
            # What was owed before, plus this month's rent billed now; never the year of past rent again.
            self.assertEqual(acc["invoiced"], Decimal("1350.00"))
            self.assertEqual(Invoice.objects.filter(lease=lease, kind=Invoice.RENT).count(), 1)
            self.assertEqual(rentals.bill_rent(today)[0], 0, "the rent job does not bill this month again")
            vacant = Home.objects.get(stand__stand_number=3)
            self.assertFalse(Lease.objects.filter(home=vacant).exists())

    def test_property_rows_must_make_sense(self):
        upload = csv_file(
            "Reference,Address,Owner first name,Owner surname,Owner mobile,Tenant first name,Tenant surname,Monthly rent (USD),Lease start,Lease end,Rent owed (USD)\n"
            "1,A,Tawanda,Makoni,0772900100,Rudo,Moyo,,2025-01-01,,\n"
            "2,B,Tawanda,Makoni,0772900100,Rudo,Moyo,400,,,\n"
            "3,C,Tawanda,Makoni,0772900100,Rudo,Moyo,400,2025-05-01,2025-01-01,\n"
            "4,D,Tawanda,Makoni,0772900100,,,,,,100\n"
            "4,E,Tawanda,Makoni,0772900100,,,,,,\n"
        )
        data = self.post("/imports/check", "properties", upload, user=self.landlord).json()
        self.assertEqual([e["row"] for e in data["errors"]], [2, 3, 4, 5, 6])

    def test_rental_balances(self):
        with use_estate(self.rental):
            self.post("/imports/run", "properties", csv_file(
                "Address,Owner first name,Owner surname,Owner mobile,Tenant first name,Tenant surname,Monthly rent (USD),Lease start\n"
                f"Flat 1,Tawanda,Makoni,0772900100,Rudo,Moyo,300,{timezone.localdate():%Y-%m-01}\nFlat 2,Tawanda,Makoni,0772900100,,,,\n"
            ), user=self.landlord)
        upload = csv_file("Reference,Balance owed (USD),Balance date\n1,250,2025-10-31\n2,10,\n3,5,\n")
        data = self.post("/imports/run", "balances", upload, user=self.landlord).json()
        self.assertEqual([e["row"] for e in data["errors"]], [3, 4])
        data = self.post("/imports/run", "balances", csv_file("Reference,Balance owed (USD)\n1,250\n2,0\n"), user=self.landlord).json()
        self.assertTrue(data["ok"], data)
        with use_estate(self.rental):
            lease = Lease.objects.get()
            opening = Invoice.objects.get(kind=Invoice.OPENING)
            self.assertEqual(opening.lease, lease)
            self.assertEqual(opening.amount_usd, Decimal("250.00"))
