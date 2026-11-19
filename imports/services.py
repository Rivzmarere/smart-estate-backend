"""Templates to fill in, and undoing an import."""

import csv
import io

from django.apps import apps
from django.db import transaction
from django.db.models.deletion import Collector, ProtectedError, RestrictedError
from django.utils import timezone

# Children first, so deleting one never takes something else with it.
UNDO_ORDER = ["levy.payment", "levy.invoice", "rentals.lease", "home.home", "stand.stand", "resident.resident", "owner.owner"]
NAMES = {
    "levy.payment": "payments", "levy.invoice": "invoices", "rentals.lease": "leases", "home.home": "homes",
    "stand.stand": "stands", "resident.resident": "residents or tenants", "owner.owner": "owners",
    "visit.visit": "visitors", "complaint.complain": "complaints", "portal.householdmember": "household members",
    "whitelist.whitelist": "regular visitors", "portal.householdrequest": "household requests",
}


class UndoRefused(Exception):
    pass


def _what(objects):
    kinds = sorted({NAMES.get(o._meta.label_lower, o._meta.verbose_name_plural) for o in objects})
    return ", ".join(kinds)


@transaction.atomic
def undo(batch, user):
    """Delete what the import created, if nothing else has been added to those records since."""
    if batch.undone_at:
        raise UndoRefused("This import was already undone.")
    labels = UNDO_ORDER + [l for l in batch.created_ids if l not in UNDO_ORDER]
    removed = 0
    for label in labels:
        ids = set(batch.created_ids.get(label) or [])
        if not ids:
            continue
        model = apps.get_model(label)
        objects = list(model.all_estates.filter(pk__in=ids, estate=batch.estate))
        if not objects:
            continue
        collector = Collector(using="default")
        try:
            collector.collect(objects)
        except (ProtectedError, RestrictedError) as exc:
            raise UndoRefused(
                f"Some of these records have been used since the import ({_what(exc.protected_objects if isinstance(exc, ProtectedError) else exc.restricted_objects)}). "
                "Change or remove them one by one instead."
            )
        extra = [o for m, found in collector.data.items() for o in found if not (m._meta.label_lower == label and o.pk in ids)]
        extra += [o for qs in collector.fast_deletes for o in qs[:20]]
        if extra:
            raise UndoRefused(
                f"Records have been added to this import's homes since ({_what(extra)}). Change or remove them one by one instead."
            )
        collector.delete()
        removed += len(objects)
    batch.undone_at = timezone.now()
    batch.undone_by = user
    batch.save(update_fields=["undone_at", "undone_by"])
    return removed


# ---------------------------------------------------------------- templates

def template_csv(importer):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([c.header for c in importer.columns])
    return out.getvalue().encode("utf-8-sig")


def template_xlsx(importer, estate):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    brand = PatternFill("solid", fgColor="405189")
    soft = PatternFill("solid", fgColor="ECEEF8")
    white = Font(bold=True, color="FFFFFF")
    bold = Font(bold=True)

    book = Workbook()
    data = book.active
    data.title = importer.sheet_title
    for i, column in enumerate(importer.columns, start=1):
        cell = data.cell(row=1, column=i, value=column.header + (" *" if column.required else ""))
        cell.font, cell.fill = white, brand
        cell.alignment = Alignment(vertical="center")
        data.column_dimensions[get_column_letter(i)].width = max(14, min(42, len(column.header) + 6))
        if column.kind in ("phone", "text", "email"):
            for row in range(2, 1002):  # keep 0772... as typed: Excel drops a leading 0 from numbers
                data.cell(row=row, column=i).number_format = "@"
        elif column.kind == "date":
            for row in range(2, 1002):
                data.cell(row=row, column=i).number_format = "yyyy-mm-dd"
        elif column.kind == "money":
            for row in range(2, 1002):
                data.cell(row=row, column=i).number_format = "0.00"
    data.freeze_panes = "A2"
    data.row_dimensions[1].height = 22

    help_sheet = book.create_sheet("Instructions")
    help_sheet.column_dimensions["A"].width = 28
    help_sheet.column_dimensions["B"].width = 90
    help_sheet.append([f"{importer.title} for {estate.name}"])
    help_sheet["A1"].font = Font(bold=True, size=14, color="405189")
    help_sheet.append([])
    for note in importer.notes:
        help_sheet.append(["", note])
    help_sheet.append(["", f'Fill in the "{importer.sheet_title}" sheet, save, and upload the file in the back office (Setup, Import).'])
    help_sheet.append(["", "Nothing is saved until every row is correct, and nothing is sent to residents."])
    help_sheet.append([])
    help_sheet.append(["Column", "What to put in it"])
    for cell in help_sheet[help_sheet.max_row]:
        cell.font, cell.fill = bold, soft
    for column in importer.columns:
        help_sheet.append([column.header + (" *" if column.required else ""), column.help or ("Required." if column.required else "Optional.")])
    help_sheet.append([])
    help_sheet.append(["Examples", "(copy the layout, not these rows)"])
    help_sheet[help_sheet.max_row][0].font = bold
    help_sheet.append([c.header for c in importer.columns])
    for cell in help_sheet[help_sheet.max_row]:
        cell.font, cell.fill = bold, soft
    for example in importer.examples:
        help_sheet.append(example)
    for row in help_sheet.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
