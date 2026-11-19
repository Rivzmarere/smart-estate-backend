"""
Reading an estate's spreadsheet (Excel .xlsx or .csv) into rows of plain values.

Estates keep their records in all sorts of spreadsheets, so this is forgiving:
headers are matched ignoring case, spaces and punctuation (and a few other
common names), the header row may be below a title, empty rows are skipped,
and money may be written "$1,200.50" or "USD 1200".
"""

import csv
import datetime
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
XLSX_SIGNATURE = b"PK\x03\x04"


class FileProblem(ValueError):
    """The file as a whole cannot be read (wrong type, no header row, missing columns)."""


@dataclass
class Column:
    key: str
    header: str
    kind: str = "text"  # text, int, money, date, yes, phone, email
    required: bool = False
    example: str = ""
    help: str = ""
    aliases: tuple = ()
    max_length: int = 0

    def names(self):
        return {squash(self.header), squash(self.key), *(squash(a) for a in self.aliases)}


@dataclass
class Sheet:
    rows: list = field(default_factory=list)  # [(spreadsheet line number, {key: raw value})]
    ignored_columns: list = field(default_factory=list)


def squash(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


# ---------------------------------------------------------------- files

def read(upload, columns):
    """Rows from an uploaded .xlsx or .csv file, keyed by column key."""
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise FileProblem("The file is bigger than 5 MB. Split it into smaller files.")
    if not data.strip():
        raise FileProblem("The file is empty.")
    name = (getattr(upload, "name", "") or "").lower()
    if data.startswith(XLSX_SIGNATURE):
        grid = _xlsx_grid(data)
    elif name.endswith((".xls", ".xlsx", ".xlsm", ".ods", ".numbers")):
        raise FileProblem("Save the spreadsheet as Excel (.xlsx) or CSV and upload it again.")
    else:
        grid = _csv_grid(data)
    return _rows(grid, columns)


def _xlsx_grid(data):
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # corrupt or not really a workbook
        raise FileProblem("This Excel file could not be opened. Save it again as .xlsx and retry.") from exc
    sheets = [s for s in book.worksheets if s.title.strip().lower() not in ("instructions", "help", "read me", "readme")]
    sheet = sheets[0] if sheets else book.worksheets[0]
    grid = []
    for values in sheet.iter_rows(values_only=True):
        grid.append(list(values))
        if len(grid) > MAX_ROWS + 50:
            break
    book.close()
    return grid


def _csv_grid(data):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1252 decodes almost anything
        raise FileProblem("The file is not a text CSV file.")
    if "\x00" in text:
        raise FileProblem("This is not a CSV file. Upload an Excel (.xlsx) or CSV file.")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def _rows(grid, columns):
    lookup = {}
    for column in columns:
        for name in column.names():
            lookup.setdefault(name, column.key)

    header_at, mapping = None, {}
    for index, values in enumerate(grid[:20]):
        found = {i: lookup[squash(v)] for i, v in enumerate(values) if squash(v) in lookup}
        if len(found) >= 2:
            header_at, mapping = index, found
            break
    if header_at is None:
        raise FileProblem(
            "No header row found. The first row should have the column names from the template, e.g. "
            + ", ".join(f'"{c.header}"' for c in columns if c.required) + "."
        )

    seen = set()
    for i, key in list(mapping.items()):
        if key in seen:
            raise FileProblem(f'The column "{_header(columns, key)}" appears twice.')
        seen.add(key)
    missing = [c.header for c in columns if c.required and c.key not in seen]
    if missing:
        raise FileProblem("Missing column" + ("s" if len(missing) > 1 else "") + ": " + ", ".join(f'"{m}"' for m in missing) + ".")

    header = grid[header_at]
    ignored = [str(v).strip() for i, v in enumerate(header) if i not in mapping and str(v or "").strip()]
    sheet = Sheet(ignored_columns=ignored)
    for index, values in enumerate(grid[header_at + 1:], start=header_at + 2):
        row = {key: (values[i] if i < len(values) else None) for i, key in mapping.items()}
        if all(_blank(v) for v in row.values()):
            continue
        sheet.rows.append((index, row))
        if len(sheet.rows) > MAX_ROWS:
            raise FileProblem(f"The file has more than {MAX_ROWS} rows. Split it into smaller files.")
    if not sheet.rows:
        raise FileProblem("The file has a header row but no rows under it.")
    return sheet


def _header(columns, key):
    return next(c.header for c in columns if c.key == key)


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


# ---------------------------------------------------------------- values

class BadValue(ValueError):
    pass


def text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def integer(value):
    raw = text(value)
    if not raw:
        return None
    try:
        number = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        raise BadValue(f'"{raw}" is not a number')
    if number != number.to_integral_value():
        raise BadValue(f'"{raw}" is not a whole number')
    return int(number)


def amount(value):
    """Money in USD. Brackets or a leading minus mean a negative amount (in credit)."""
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    raw = text(value)
    if not raw or raw in ("-", "—"):
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"(?i)usd|us\$|\$|,|\s|\(|\)", "", raw)
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        raise BadValue(f'"{raw}" is not an amount of money')
    return (-number if negative else number).quantize(Decimal("0.01"))


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d %B %Y", "%d %b %Y", "%Y/%m/%d")


def date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    raw = text(value)
    if not raw:
        return None
    if re.fullmatch(r"\d{5}", raw):  # an Excel date number in a CSV
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(raw))
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise BadValue(f'"{raw}" is not a date (write it like 2025-03-31 or 31/03/2025)')


YES = {"yes", "y", "true", "1", "x", "owner", "ndiyo", "yebo"}
NO = {"no", "n", "false", "0", "aiwa", "hayi"}


def yes(value):
    raw = text(value).lower()
    if not raw:
        return None
    if raw in YES:
        return True
    if raw in NO:
        return False
    raise BadValue(f'"{text(value)}" should be Yes or No')


def phone(value):
    """A Zimbabwean or international number, stored the way the rest of the system does (0771234567)."""
    raw = text(value)
    if not raw:
        return ""
    first = re.split(r"[/;]|\bor\b", raw)[0]
    digits = re.sub(r"\D", "", first)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("263") and len(digits) == 12:
        digits = "0" + digits[3:]
    elif len(digits) == 9 and digits[0] in "78":
        digits = "0" + digits
    if not 9 <= len(digits) <= 15:
        raise BadValue(f'"{raw}" is not a phone number')
    return digits


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email(value):
    raw = text(value)
    if raw and not EMAIL.match(raw):
        raise BadValue(f'"{raw}" is not an email address')
    return raw.lower()


PARSERS = {"text": text, "int": integer, "money": amount, "date": date, "yes": yes, "phone": phone, "email": email}


def clean(columns, raw):
    """({key: value}, {key: problem}) for one row."""
    values, problems = {}, {}
    for column in columns:
        if column.key not in raw:
            values[column.key] = PARSERS[column.kind](None)
            continue
        try:
            value = PARSERS[column.kind](raw[column.key])
        except BadValue as exc:
            problems[column.key] = str(exc)
            continue
        if column.required and value in ("", None):
            problems[column.key] = "is empty"
            continue
        if column.max_length and isinstance(value, str) and len(value) > column.max_length:
            problems[column.key] = f"is longer than {column.max_length} characters"
            continue
        values[column.key] = value
    return values, problems
