"""
Bulk import from Excel or CSV.

    GET  imports                 what this estate can import, with the columns, and past imports
    GET  imports/template?kind=homes&type=xlsx|csv
    POST imports/check           (multipart: kind, file) check the file, save nothing
    POST imports/run             (multipart: kind, file) check and save, all or nothing
    POST imports/<id>/undo       remove what an import added, while nothing depends on it
"""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from estates.context import ALL, current_estate
from smartEstateBackend.permissions import IsAdminRole

from . import services
from .importers import IMPORTERS, for_estate
from .models import ImportBatch
from .reader import FileProblem, read


def estate_or_error():
    estate = current_estate()
    if estate is None or estate is ALL:
        return None, Response({"detail": "Choose an estate first."}, status=400)
    return estate, None


def importer_for(estate, kind):
    cls = IMPORTERS.get(kind or "")
    if cls is None or estate.kind not in cls.estate_kinds:
        return None
    return cls


def batch_row(batch):
    who = batch.created_by
    return {
        "id": batch.id, "kind": batch.kind, "title": IMPORTERS[batch.kind].title if batch.kind in IMPORTERS else batch.kind,
        "filename": batch.filename, "rows": batch.rows, "summary": batch.summary, "created_at": batch.created_at,
        "created_by": (who.get_full_name() or who.username) if who else "", "undone_at": batch.undone_at,
    }


class Imports(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        estate, problem = estate_or_error()
        if problem:
            return problem
        kinds = [
            {"kind": cls.kind, "title": cls.title, "notes": cls.notes,
             "columns": [{"header": c.header, "required": c.required, "help": c.help} for c in cls.columns]}
            for cls in for_estate(estate)
        ]
        history = [batch_row(b) for b in ImportBatch.objects.select_related("created_by")[:50]]
        return Response({"estate_kind": estate.kind, "kinds": kinds, "history": history})


class Template(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        estate, problem = estate_or_error()
        if problem:
            return problem
        cls = importer_for(estate, request.query_params.get("kind"))
        if cls is None:
            return Response({"detail": "Unknown import."}, status=400)
        name = f"{slugify(estate.name) or 'estate'}-{cls.kind}"
        if request.query_params.get("type") == "csv":
            response = HttpResponse(services.template_csv(cls), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
        else:
            response = HttpResponse(
                services.template_xlsx(cls, estate),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="{name}.xlsx"'
        return response


class RunImport(APIView):
    """check: commit=False; run: commit=True."""

    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]
    commit = False

    def post(self, request):
        estate, problem = estate_or_error()
        if problem:
            return problem
        cls = importer_for(estate, request.data.get("kind"))
        if cls is None:
            return Response({"detail": "Choose what you are importing."}, status=400)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Choose the file to upload."}, status=400)
        try:
            sheet = read(upload, cls.columns)
        except FileProblem as exc:
            return Response({"ok": False, "detail": str(exc), "errors": [], "warnings": [], "preview": [], "counts": {}}, status=400)
        result = cls(estate, request.user).run(sheet, commit=self.commit, filename=upload.name or "")
        data = result.as_dict()
        if result.batch:
            from audit.log import record

            record("import.run", f"Imported {cls.title.lower()} from {upload.name} ({result.rows} rows)", result.batch, area="data", counts=data["counts"])
        if self.commit:
            return Response(data, status=201 if result.batch else 400)
        return Response(data)


class CheckImport(RunImport):
    commit = False


class SaveImport(RunImport):
    commit = True


class UndoImport(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, id):
        estate, problem = estate_or_error()
        if problem:
            return problem
        batch = get_object_or_404(ImportBatch, pk=id)
        try:
            removed = services.undo(batch, request.user)
        except services.UndoRefused as exc:
            return Response({"detail": str(exc)}, status=400)
        from audit.log import record

        record("import.undone", f"Undid the import of {batch.filename} ({removed} records removed)", batch, area="data")
        return Response({**batch_row(batch), "removed": removed})
