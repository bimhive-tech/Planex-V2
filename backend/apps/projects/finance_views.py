"""Project finances API: monthly cash flow + invoices.

Money is gated separately from general project access: reads need VIEW_FINANCES
(or MANAGE_FINANCES), writes need MANAGE_FINANCES."""
import mimetypes

from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import Permission

from .finance_imports import import_cashflow, import_dashboard, import_invoices
from .models import CashFlowEntry, DashboardImport, Invoice, Project

MAX_IMPORT_BYTES = 40 * 1024 * 1024


def _project(request, project_id):
    try:
        return Project.objects.get(pk=project_id, company=request.user.company)
    except (Project.DoesNotExist, ValueError, TypeError):
        raise NotFound("Project not found.")


def _require_view_finances(request):
    perms = request.user.effective_permissions()
    if Permission.VIEW_FINANCES.value not in perms and Permission.MANAGE_FINANCES.value not in perms:
        raise PermissionDenied("You don't have permission to view finances.")


def _require_manage_finances(request):
    if Permission.MANAGE_FINANCES.value not in request.user.effective_permissions():
        raise PermissionDenied("You don't have permission to manage finances.")


# --- Cash flow -------------------------------------------------------------

class CashFlowEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowEntry
        fields = ["id", "month", "planned", "actual"]


class CashFlowView(APIView):
    """List, or bulk-replace, a project's monthly cash-flow rows. Bulk replace
    keeps the grid UX trivial (edit the table, save the whole thing atomically)."""

    permission_classes = [IsAuthenticated]

    def _payload(self, project):
        return {
            "entries": CashFlowEntrySerializer(project.cashflow_entries.all(), many=True).data,
            "currency": project.display_currency or "",
        }

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view_finances(request)
        return Response(self._payload(project))

    def put(self, request, project_id):
        project = _project(request, project_id)
        _require_manage_finances(request)
        rows = request.data if isinstance(request.data, list) else request.data.get("entries", [])
        serializer = CashFlowEntrySerializer(data=rows, many=True)
        serializer.is_valid(raise_exception=True)
        # Normalise to the 1st of each month and let the latest row for a month win
        # so the (project, month) unique constraint can't be violated.
        by_month = {}
        for row in serializer.validated_data:
            month = row["month"].replace(day=1)
            by_month[month] = CashFlowEntry(
                company=project.company, project=project, month=month,
                planned=row.get("planned") or 0, actual=row.get("actual") or 0,
            )
        with transaction.atomic():
            project.cashflow_entries.all().delete()
            CashFlowEntry.objects.bulk_create(by_month.values())
        return Response(self._payload(project))


class CashFlowImportView(APIView):
    """Import a project's monthly cash flow from an Excel workbook, replacing the
    current rows. Accepts the wide site-office layout (months across a row) or a
    simple Month/Planned/Actual table."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require_manage_finances(request)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file uploaded."})
        if not upload.name.lower().endswith((".xlsx", ".xlsm")):
            raise ValidationError({"file": "Upload an .xlsx or .xlsm file."})
        if upload.size > MAX_IMPORT_BYTES:
            raise ValidationError({"file": "File is too large (max 40 MB)."})
        try:
            result = import_cashflow(project, upload)
        except ValueError as exc:
            raise ValidationError({"file": str(exc)})
        except Exception as exc:  # a corrupt workbook shouldn't 500
            raise ValidationError({"file": f"Couldn't read this workbook: {exc}"})
        return Response(result)


def _checked_upload(request):
    """The request's uploaded workbook, or a 400 explaining what's wrong."""
    upload = request.FILES.get("file")
    if not upload:
        raise ValidationError({"file": "No file uploaded."})
    if not upload.name.lower().endswith((".xlsx", ".xlsm")):
        raise ValidationError({"file": "Upload an .xlsx or .xlsm file."})
    if upload.size > MAX_IMPORT_BYTES:
        raise ValidationError({"file": "File is too large (max 40 MB)."})
    return upload


def _data_date(request, upload):
    """The date an upload's figures are as of: the `date` the import dialog
    sent, else one read from the filename ("… 02-08-2026.xlsx"), else None —
    the same order a schedule import uses, so one dialog means the same thing
    for either file."""
    import datetime

    from .imports import parse_date_from_name

    raw = request.data.get("date")
    if raw:
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            raise ValidationError({"date": "Use YYYY-MM-DD."})
    return parse_date_from_name(upload.name or "")


class DashboardImportSerializer(serializers.ModelSerializer):
    """One past dashboard upload, for the Finances tab's history list."""

    uploaded_by_name = serializers.CharField(
        source="uploaded_by.full_name", read_only=True, default="")
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = DashboardImport
        fields = ["id", "source", "data_date", "created_at", "uploaded_by_name", "summary", "file_url"]

    def get_file_url(self, obj):
        if not obj.file:
            return None
        return f"/api/projects/{obj.project_id}/dashboard/imports/{obj.id}/file/"


class DashboardImportView(APIView):
    """One upload for the whole dashboard workbook — cash flow, the progress
    curve behind the report's S-curve, and the invoice extracts.

    The same file feeds all three and used to need uploading once per panel
    (client ask, 2026-09-09). A workbook carrying only some of those sheets
    imports what it has: parts whose layout isn't present come back under
    `skipped` rather than failing the upload, so one missing sheet can't hide
    what the others brought in."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require_manage_finances(request)
        upload = _checked_upload(request)
        data_date = _data_date(request, upload)
        result = import_dashboard(project, upload)
        if not result["imported"]:
            # Nothing at all was recognised — that IS a failed upload, and the
            # reasons are more use to the reader than a generic refusal.
            raise ValidationError({"file": " ".join(result["skipped"].values())
                                   or "Nothing in this workbook could be imported."})
        # Record the upload only once it has actually imported something, so
        # the history is a list of what changed the project's figures rather
        # than of every file anyone tried. Keeping the workbook makes the row
        # answerable — "where did these invoice figures come from?" ends in a
        # download, not in asking whoever uploaded it.
        record = DashboardImport(
            company=project.company, project=project, source=(upload.name or "")[:200],
            data_date=data_date, uploaded_by=request.user, summary=result)
        upload.seek(0)
        record.file.save(upload.name or "dashboard.xlsx", upload, save=False)
        record.save()
        return Response(result)


# --- Invoices --------------------------------------------------------------

class InvoiceSerializer(serializers.ModelSerializer):
    has_image = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ["id", "name", "value", "date", "sort_order", "has_image"]

    def get_has_image(self, obj):
        return bool(obj.image)


class InvoiceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ["name", "value", "date", "image", "sort_order"]


class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view_finances(request)
        return Response(InvoiceSerializer(project.invoices.all(), many=True).data)

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require_manage_finances(request)
        serializer = InvoiceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save(company=project.company, project=project, created_by=request.user)
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class InvoiceImportView(APIView):
    """Import invoices from an extract-comparison workbook (a per-BOQ-item
    matrix, one column per submitted extract). Upserts by (name, date) so a
    re-import never touches invoices entered by hand or their attached scans."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, project_id):
        project = _project(request, project_id)
        _require_manage_finances(request)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "No file uploaded."})
        if not upload.name.lower().endswith((".xlsx", ".xlsm")):
            raise ValidationError({"file": "Upload an .xlsx or .xlsm file."})
        if upload.size > MAX_IMPORT_BYTES:
            raise ValidationError({"file": "File is too large (max 40 MB)."})
        try:
            result = import_invoices(project, upload)
        except ValueError as exc:
            raise ValidationError({"file": str(exc)})
        except Exception as exc:  # a corrupt workbook shouldn't 500
            raise ValidationError({"file": f"Couldn't read this workbook: {exc}"})
        return Response(result)


class InvoiceDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _get(self, project, invoice_id):
        try:
            return Invoice.objects.get(pk=invoice_id, project=project)
        except (Invoice.DoesNotExist, ValueError, TypeError):
            raise NotFound("Invoice not found.")

    def patch(self, request, project_id, invoice_id):
        project = _project(request, project_id)
        _require_manage_finances(request)
        invoice = self._get(project, invoice_id)
        serializer = InvoiceWriteSerializer(invoice, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(InvoiceSerializer(invoice).data)

    def delete(self, request, project_id, invoice_id):
        project = _project(request, project_id)
        _require_manage_finances(request)
        invoice = self._get(project, invoice_id)
        if invoice.image:
            invoice.image.delete(save=False)
        invoice.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvoiceImageView(APIView):
    """Stream an invoice scan through an authed, tenant-scoped endpoint (no public
    URL — works the same on local disk and R2)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, invoice_id):
        project = _project(request, project_id)
        _require_view_finances(request)
        invoice = get_object_or_404(Invoice, pk=invoice_id, project=project)
        if not invoice.image:
            raise Http404
        content_type = mimetypes.guess_type(invoice.image.name)[0] or "application/octet-stream"
        return FileResponse(invoice.image.open("rb"), content_type=content_type)


class DashboardImportHistoryView(APIView):
    """What dashboard workbooks have been imported into this project — file,
    when, and who uploaded it (register item D2).

    Read-only. These rows are a log of uploads, not retained batches: the cash
    flow, curve points and invoices a workbook wrote are replaced or upserted
    by the next one, so there is nothing here to restore or switch between.
    Small list (one row per upload), so no pagination."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _project(request, project_id)
        _require_view_finances(request)
        rows = project.dashboard_imports.select_related("uploaded_by")[:50]
        return Response(DashboardImportSerializer(rows, many=True).data)


class DashboardImportFileView(APIView):
    """Stream one past dashboard workbook — same private, tenant-scoped
    pattern as ScheduleImportFileView."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, import_id):
        project = _project(request, project_id)
        _require_view_finances(request)
        try:
            record = project.dashboard_imports.get(pk=import_id)
        except (DashboardImport.DoesNotExist, ValueError, TypeError):
            raise NotFound("Import not found.")
        if not record.file:
            raise Http404
        content_type = mimetypes.guess_type(record.file.name)[0] or "application/octet-stream"
        return FileResponse(record.file.open("rb"), content_type=content_type,
                            filename=record.source or "dashboard.xlsx")
