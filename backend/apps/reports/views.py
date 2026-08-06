"""Reports API. Company-scoped CRUD for templates + reports, plus PDF download.

Access: EXPORT_REPORTS gates everything — viewing, downloading, and editing.
Reports are sensitive deliverables, so a role without it (e.g. a site engineer)
sees no reports at all, not just a hidden download button.
"""
import json

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.constants import Permission

from .constants import apply_report_layout_override, merged_config
from .layout_seed import seed_layout_from_sections
from .models import Report, ReportTemplate
from .pdf import build_report_pdf
from .pdf_canvas import build_canvas_pdf, has_canvas_layout
from .serializers import (
    ReportListSerializer,
    ReportTemplateSerializer,
    ReportWriteSerializer,
)
from .services import build_report_context

class ReportsAccess(BasePermission):
    """EXPORT_REPORTS gates all report/template access — read, download, edit."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return Permission.EXPORT_REPORTS in user.effective_permissions()


def _render_report_pdf(report, engine):
    """Shared by the `pdf` and `page-images` actions — same cfg/context
    assembly and canvas-vs-legacy dispatch either way. Returns (bytes,
    section->page map)."""
    ctx = build_report_context(report)
    cfg = merged_config(report.template.config if report.template else None)
    cfg = apply_report_layout_override(cfg, report)
    pages = {}
    if engine == "canvas" or (engine is None and has_canvas_layout(cfg)):
        data = build_canvas_pdf(report, ctx, cfg=cfg, out_pages=pages)
    else:
        data = build_report_pdf(report, ctx, out_pages=pages, cfg=cfg)
    return data, pages


class ReportTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ReportsAccess]
    serializer_class = ReportTemplateSerializer

    def get_queryset(self):
        return ReportTemplate.objects.filter(company=self.request.user.company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    @action(detail=True, methods=["post"], url_path="seed-layout")
    def seed_layout(self, request, pk=None):
        """"Start from my current sections" — build a canvas layout from this
        template's existing Content & Labels config. Overwrites any existing
        page_design/layout on the template with the seeded starting point."""
        template = self.get_object()
        cfg = merged_config(template.config)
        seeded = seed_layout_from_sections(cfg)
        config = dict(template.config or {})
        config["page_design"] = seeded["page_design"]
        config["layout"] = seeded["layout"]
        template.config = config
        template.save(update_fields=["config", "updated_at"])
        return Response(ReportTemplateSerializer(template).data)


class ReportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ReportsAccess]

    def get_queryset(self):
        qs = Report.objects.filter(company=self.request.user.company).select_related(
            "project", "template"
        )
        if self.action == "list":
            project = self.request.query_params.get("project")
            if project:
                qs = qs.filter(project_id=project)
        return qs

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ReportWriteSerializer
        return ReportListSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def data(self, request, pk=None):
        """The computed report data (project info + progress tables) so the
        builder can show what's pulled from the chosen project, live."""
        report = self.get_object()
        ctx = build_report_context(report)
        # `images` (the detailed-progress zone grids' inline photos) and
        # _progress (an internal per-activity map, can be tens of thousands
        # of entries) are only ever read at PDF-render time.
        for key in ("images", "_progress", "zone_grids"):
            ctx.pop(key, None)

        def light(entry):
            """Caption/url only — never the raw storage path — so the
            Customize tab's canvas can render <img src={url}> (an authed,
            tenant-scoped streaming endpoint, not a public bucket URL) and
            count/label a repeating page's real instances without the
            browser ever seeing where the file actually lives."""
            return {"caption": entry.get("caption") or "", "url": entry.get("url") or ""} if entry else None

        logos = ctx.get("logos") or {}
        ctx["logos"] = {
            "left": light(logos.get("left")),
            "right": light(logos.get("right")),
            "cover": light(logos.get("cover")),
            "extra": [light(e) for e in logos.get("extra") or []],
        }
        ctx["photos"] = [light(p) for p in ctx.get("photos") or []]
        ctx["attachments"] = [light(a) for a in ctx.get("attachments") or []]
        # area_dashboards keeps everything an item-scoped element
        # (item.duration/item.units/item.children) needs to resolve real
        # data, minus its own nested per-zone photos (a separate concern).
        ctx["area_dashboards"] = [
            {k: v for k, v in a.items() if k != "photos"} for a in ctx.get("area_dashboards") or []
        ]
        return Response(ctx)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Generate and stream the report PDF on demand.

        `?engine=canvas`/`?engine=sections` force a specific renderer (useful
        while the canvas engine is being built out); otherwise a template
        with real Page Designer / Report Configuration content uses the new
        canvas engine and everything else keeps using Content & Labels."""
        report = self.get_object()
        data, pages = _render_report_pdf(report, request.query_params.get("engine"))
        resp = HttpResponse(data, content_type="application/pdf")
        safe = (report.report_number or report.title or "report").replace("/", "-")
        resp["Content-Disposition"] = f'inline; filename="report-{safe}.pdf"'
        # Section -> page map so the builder tabs can scroll the preview.
        resp["X-Section-Pages"] = json.dumps(pages)
        resp["Access-Control-Expose-Headers"] = "X-Section-Pages"
        return resp

    @action(detail=True, methods=["get"], url_path="page-images")
    def page_images(self, request, pk=None):
        """Every page of the report's current PDF, rasterized to PNG.

        The Customize tab's canvas uses these as each page's real background
        — pixel-identical to the actual PDF — instead of trying to render
        the PDF in the browser (pdf.js's own network-stream fetcher hangs
        mid-render against this app's PDF route; see lib/pdfWorker.ts on the
        frontend for the same issue in the plain preview panel). Rasterizing
        server-side with PyMuPDF, which already ships for the P6 export
        pipeline, sidesteps that entirely. Generated once per request (same
        "regenerate on save, not on every edit" model as the PDF endpoint),
        not cached — a report's layout_override changes between calls.
        """
        import base64

        import fitz

        report = self.get_object()
        data, _ = _render_report_pdf(report, request.query_params.get("engine"))
        doc = fitz.open(stream=data, filetype="pdf")
        dpi = 144
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            pages.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
        return Response({"pages": pages, "dpi": dpi})
