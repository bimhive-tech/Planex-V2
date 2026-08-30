"""Reports API. Company-scoped CRUD for templates + reports, plus PDF download.

Access: EXPORT_REPORTS gates everything — viewing, downloading, and editing.
Reports are sensitive deliverables, so a role without it (e.g. a site engineer)
sees no reports at all, not just a hidden download button.
"""
import json

from django.core.cache import cache
from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.constants import Permission

from .constants import merge_layout_override, merged_config
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


_UNSET = object()

# build_report_context is the expensive part of every render (assembles every
# zone/activity/cashflow/etc. the project has) but doesn't depend on layout at
# all — only on the report's own project/date/scope, none of which change
# while you're rearranging elements on the Customize tab. Cached briefly and
# only for chart_svgs/table_data (the Customize tab's live, per-element
# previews — see their docstrings): the first one in an editing session pays
# the cost once, every call after that skips straight to rendering. `pdf`/
# `data` deliberately stay uncached so anything actually saved or downloaded
# always reflects current project data. TTL, not invalidate-on-write, since
# it only ever backs transient in-editor previews — worst case is a few
# minutes of staleness in those, never in what's actually saved/downloaded.
_CONTEXT_CACHE_TTL = 300


def _cached_report_context(report):
    key = f"report-context:{report.id}"
    ctx = cache.get(key)
    if ctx is None:
        ctx = build_report_context(report)
        cache.set(key, ctx, _CONTEXT_CACHE_TTL)
    return ctx


def _render_report_pdf(report, engine, override=_UNSET):
    """Shared by the `pdf` action and anything else that needs the whole
    rendered document. Returns (bytes, section->page map). The Content &
    Labels builder tab is gone from the UI, but existing templates that only
    ever had section toggles (no real canvas content) still need this
    fallback to render at all.

    `override` defaults to the report's own saved `layout_override`; pass an
    explicit dict (or None) to render a different layout instead."""
    ctx = build_report_context(report)
    cfg = merged_config(report.template.config if report.template else None)
    applied = getattr(report, "layout_override", None) if override is _UNSET else override
    cfg = merge_layout_override(cfg, applied)
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
        from .pdf_base import resolve_arabic

        report = self.get_object()
        ctx = build_report_context(report)
        # Single global direction, not a per-element guess — mirrors exactly
        # what the real PDF's own elements (see pdf_canvas._draw_toc_element)
        # use, so e.g. the TOC's page-number column sits on the same side
        # for every row regardless of that row's own page name being Arabic
        # or English/mixed.
        cfg = merged_config(report.template.config if report.template else None)
        ctx["arabic"] = resolve_arabic(cfg, ctx["project"])
        # `images` (the detailed-progress zone grids' inline photos) and
        # _progress (an internal per-activity map, can be tens of thousands
        # of entries) are only ever read at PDF-render time.
        for key in ("images", "_progress", "zone_grids", "activity_schedule"):
            ctx.pop(key, None)
        # Full activity_schedule is lazy (tens of thousands of rows, see
        # pdf_canvas._resolve_activity_schedule_table) — the builder's canvas
        # preview only needs a small real sample to show what the columns
        # look like, not the whole list.
        ctx["activity_schedule"] = list(report.project.activities.order_by("sort_order", "name").values(
            "name", "baseline_duration", "original_duration", "actual_duration",
            "remaining_duration", "schedule_performance_index", "schedule_variance",
        )[:20])

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

        `?engine=canvas`/`?engine=sections` force a specific renderer;
        otherwise a template with real Page Designer / Report Configuration
        content uses the canvas engine and anything else (an older template
        that only ever had Content & Labels toggles) falls back to it."""
        report = self.get_object()
        data, pages = _render_report_pdf(report, request.query_params.get("engine"))
        resp = HttpResponse(data, content_type="application/pdf")
        safe = (report.report_number or report.title or "report").replace("/", "-")
        resp["Content-Disposition"] = f'inline; filename="report-{safe}.pdf"'
        # Section -> page map so the builder tabs can scroll the preview.
        resp["X-Section-Pages"] = json.dumps(pages)
        resp["Access-Control-Expose-Headers"] = "X-Section-Pages"
        return resp

    @action(detail=True, methods=["post"], url_path="chart-svgs")
    def chart_svgs(self, request, pk=None):
        """Live per-chart-element SVGs for the Customize tab canvas.

        Built from the exact same Drawing objects pdf_canvas.resolve_chart
        produces for the real PDF — reportlab.graphics.renderSVG just exports
        that same shape tree to SVG instead of drawing it into a page, so
        there's no second chart implementation to keep visually in sync.
        Skips PDF assembly and PyMuPDF rasterization entirely (resolves only
        the chart elements actually on the draft, not a whole document),
        so — combined with the cached report context — this is cheap enough
        to call on every edit, not just on an explicit refresh.

        Keyed by element id; "too_small"/"no_data" statuses mirror exactly
        what the real PDF itself draws in those same cases (see
        pdf_canvas._draw_chart_element) — never a fake/placeholder chart.

        Only meaningful with a real layout_override from the report
        Customize tab: pages arriving there are already expanded to concrete,
        uniquely-id'd pages (see expandRepeatingPages on the frontend), so
        expand_pages here never re-multiplies a page and every element id in
        the response is unique. Not used by the project-agnostic Template
        Builder, which has no real project data for a chart to match anyway.
        """
        from reportlab.graphics import renderSVG
        from reportlab.lib.units import mm as _mm

        from .pdf_base import ensure_fonts
        from .pdf_canvas import MIN_CHART_H_MM, MIN_CHART_W_MM, expand_pages, resolve_chart

        report = self.get_object()
        override = request.data.get("layout_override")
        ctx = _cached_report_context(report)
        cfg = merged_config(report.template.config if report.template else None)
        applied = override if override is not None else getattr(report, "layout_override", None)
        cfg = merge_layout_override(cfg, applied)

        ensure_fonts()  # normally done inside build_canvas_pdf — this path skips that entirely
        min_w, min_h = MIN_CHART_W_MM * _mm, MIN_CHART_H_MM * _mm
        charts = {}
        for inst in expand_pages(cfg, ctx, report):
            for el in inst.page.get("elements", []):
                if el.get("type") != "chart":
                    continue
                props = el.get("props") or {}
                w, h = float(el.get("w", 0)) * _mm, float(el.get("h", 0)) * _mm
                if w < min_w or h < min_h:
                    charts[el["id"]] = {"status": "too_small"}
                    continue
                drawing = resolve_chart(
                    props.get("source", ""), props.get("chart_type"), cfg, ctx, inst.scope, w, h,
                    scope_zone_id=props.get("scope_zone_id"),
                )
                if drawing is None:
                    charts[el["id"]] = {"status": "no_data"}
                    continue
                charts[el["id"]] = {"status": "ok", "svg": renderSVG.drawToString(drawing)}
        return Response({"charts": charts})

    @action(detail=True, methods=["post"], url_path="table-data")
    def table_data(self, request, pk=None):
        """Live per-table-element data for the Customize tab canvas.

        Returns the exact same header/rows resolve_table computes for the
        real PDF table (same query, same formatting — see resolve_table's
        raw=True mode) as plain JSON, not a rendered image of any kind: the
        canvas builds a real HTML table from this, so it's actual selectable
        text, not a snapshot. "no_data" mirrors exactly the case the real
        PDF draws its own placeholder for (see pdf_canvas._draw_table_element)
        — never fake rows.

        Also returns each table's own effective `style`: the real colors/
        toggles/font size pdf_tables.py's table builders actually draw with
        (cfg["colors"]/cfg["table"]/cfg["fonts"], patched by this element's
        own zebra/border/header_bg/etc props if it sets any — see
        pdf_tables.table_style_override, the same helper resolve_table
        itself uses for the real PDF, so this can never show a look the PDF
        doesn't also produce). Per element, not one shared style for the
        whole report — a table with its own style override needs its own
        effective colors, not the report's defaults.

        `props.overrides` (the same element's manually-edited cells, see
        pdf_tables.apply_table_overrides) IS read and applied here — the
        same overrides the real PDF applies in _draw_table_element, so an
        edit made in this live preview always matches what gets downloaded.

        Same Customize-tab-only scoping as chart_svgs — see its docstring.
        """
        from reportlab.lib.units import mm as _mm

        from .pdf_canvas import expand_pages, resolve_table
        from .pdf_tables import table_style_override

        report = self.get_object()
        override = request.data.get("layout_override")
        ctx = _cached_report_context(report)
        cfg = merged_config(report.template.config if report.template else None)
        applied = override if override is not None else getattr(report, "layout_override", None)
        cfg = merge_layout_override(cfg, applied)

        def effective_style(props):
            patched = table_style_override(cfg, props)
            c, tcfg, fonts = patched["colors"], patched["table"], patched["fonts"]
            return {
                "header_bg": c["table_header_bg"], "header_text": c["table_header_text"],
                "border_color": c["table_border"], "zebra_color": c["table_row_alt"],
                "border": bool(tcfg.get("border", True)), "zebra": bool(tcfg.get("zebra")),
                "header_bold": bool(tcfg.get("header_bold")),
                "font_size": fonts["base_size"], "cell_padding": tcfg.get("cell_padding", 6),
            }

        tables = {}
        for inst in expand_pages(cfg, ctx, report):
            for el in inst.page.get("elements", []):
                if el.get("type") != "table":
                    continue
                props = el.get("props") or {}
                source = props.get("source", "")
                w = float(el.get("w", 0)) * _mm
                grid = resolve_table(
                    source, cfg, ctx, inst.scope, avail_width=w, raw=True, overrides=props.get("overrides"),
                    style=props, scope_zone_id=props.get("scope_zone_id"),
                )
                style = effective_style(props)
                if grid is None:
                    tables[el["id"]] = {"status": "no_data", "style": style}
                    continue
                tables[el["id"]] = {"status": "ok", "style": style, **grid}

        return Response({"tables": tables})

    @action(detail=True, methods=["post"], url_path="table-overflow")
    def table_overflow(self, request, pk=None):
        """Real continuation-page row data for the Customize tab canvas.

        A table with more rows than fit its box continues onto extra
        synthetic pages in the real PDF (pdf_canvas._expand_table_overflow)
        — until now the editor just clipped the box and said so (see
        ElementPreview's OverflowClip), which is honest about what won't
        fit but still didn't let you see or check the rest of it without
        downloading. This runs that exact same overflow pass and returns,
        for every table that split, the extra chunks' real row data (same
        raw=True shape table_data returns) so the frontend can synthesize
        real continuation pages in its own page list — not by re-splitting
        anything itself, which could drift from the real PDF's own
        row-per-page boundaries, but by reading them straight off the same
        ReportLab `Table.split()` calls that decide them for the download.

        Keyed by the ORIGINAL element's id -> an ordered list of chunks,
        each chunk being everything AFTER what already shows on that
        element's own (first) page — chunk[0] here is the box's SECOND
        page of rows, not its first.
        """
        from reportlab.lib.units import mm as _mm

        from .pdf_canvas import (
            _expand_description_overflow, _expand_table_overflow, _page_size_mm, el_box, expand_pages, resolve_table,
        )
        from .pdf_tables import table_style_override

        report = self.get_object()
        override = request.data.get("layout_override")
        ctx = _cached_report_context(report)
        cfg = merged_config(report.template.config if report.template else None)
        applied = override if override is not None else getattr(report, "layout_override", None)
        cfg = merge_layout_override(cfg, applied)
        design = cfg.get("page_design") or {}

        def effective_style(props):
            patched = table_style_override(cfg, props)
            c, tcfg, fonts = patched["colors"], patched["table"], patched["fonts"]
            return {
                "header_bg": c["table_header_bg"], "header_text": c["table_header_text"],
                "border_color": c["table_border"], "zebra_color": c["table_row_alt"],
                "border": bool(tcfg.get("border", True)), "zebra": bool(tcfg.get("zebra")),
                "header_bold": bool(tcfg.get("header_bold")),
                "font_size": fonts["base_size"], "cell_padding": tcfg.get("cell_padding", 6),
            }

        instances = expand_pages(cfg, ctx, report)
        instances = _expand_description_overflow(instances, cfg, ctx, design)
        instances = _expand_table_overflow(instances, cfg, ctx, design)

        continuations = {}
        i = 0
        while i < len(instances):
            inst = instances[i]
            if not inst.table_chunk0:
                i += 1
                continue
            el_id, chunk0 = next(iter(inst.table_chunk0.items()))
            el = next((e for e in (inst.page.get("elements") or []) if e.get("id") == el_id), None)
            j = i + 1
            chunk_flowables = [chunk0]
            while j < len(instances) and instances[j].continues_element and instances[j].continues_element.get("id") == el_id:
                chunk_flowables.append(instances[j].continues_chunk)
                j += 1
            if el is not None and len(chunk_flowables) > 1:
                props = el.get("props") or {}
                _, page_h_mm = _page_size_mm(design, inst.page)
                w = el_box(el, page_h_mm)[2]
                grid = resolve_table(
                    props.get("source", ""), cfg, ctx, inst.scope, avail_width=w, raw=True,
                    overrides=props.get("overrides"), style=props, scope_zone_id=props.get("scope_zone_id"),
                )
                if grid is not None:
                    style = effective_style(props)
                    rows = grid["rows"]
                    # Only a "data"/"hierarchy" table sets repeatRows=1 (see
                    # pdf_tables.py's _data_table/_hierarchy_table) — its
                    # header genuinely repeats as row 0 of every split
                    # chunk. _info_table (the 2-col key/value kind) doesn't:
                    # every one of its rows is a distinct real field, there's
                    # no repeatable "header" to speak of. Assuming every
                    # chunk always carries a duplicated header row (regardless
                    # of kind) silently dropped an info table's real last row
                    # — found live testing this exact endpoint (2026-08-26),
                    # then confirmed as a genuine bug in the real PDF too
                    # (that row really was landing on its own orphaned,
                    # near-blank continuation page there), not just here.
                    header_rows = 1 if grid["kind"] != "info" else 0
                    offset = len(chunk0._cellvalues) - header_rows
                    chunks = []
                    for flowable in chunk_flowables[1:]:
                        count = len(flowable._cellvalues) - header_rows
                        chunks.append({
                            "status": "ok", "kind": grid["kind"], "header": grid["header"],
                            "rows": rows[offset:offset + count], "style": style,
                        })
                        offset += count
                    continuations[el_id] = chunks
            i = j

        return Response({"continuations": continuations})

    @action(detail=True, methods=["post"], url_path="toc-entries")
    def toc_entries(self, request, pk=None):
        """Live "List of tables/figures/images" content for the Customize
        tab canvas.

        The "Contents" TOC variant already renders for real in the editor —
        it only needs this report's own page list, which the frontend has
        anyway (see ReportConfigurator's tocEntries). The other three
        variants ("tables"/"figures"/"images") number every OTHER captioned
        element in final PDF order, which depends on the whole document
        (repeat-page expansion, table-overflow pagination pushing later
        pages' numbers up) — not something the per-page canvas editor can
        recompute on its own, so until now it just showed a "resolved in the
        downloaded PDF" placeholder there (see ElementPreview.tsx's
        TocPreview). Runs the exact same pre-pass build_canvas_pdf runs
        before it draws anything (expand_pages -> overflow expansion ->
        pdf_canvas._collect_captions), so this can never drift from what the
        downloaded PDF actually lists.

        Same Customize-tab-only scoping as chart_svgs/table_data.
        """
        from .pdf_canvas import (
            _collect_captions, _expand_description_overflow, _expand_table_overflow, _expand_toc_overflow,
            expand_pages,
        )

        report = self.get_object()
        override = request.data.get("layout_override")
        ctx = _cached_report_context(report)
        cfg = merged_config(report.template.config if report.template else None)
        applied = override if override is not None else getattr(report, "layout_override", None)
        cfg = merge_layout_override(cfg, applied)

        design = cfg.get("page_design") or {}
        instances = expand_pages(cfg, ctx, report)
        instances = _expand_description_overflow(instances, cfg, ctx, design)
        instances = _expand_table_overflow(instances, cfg, ctx, design)
        _collect_captions(instances, cfg, ctx)
        # A captioned list can itself run past its own box (see
        # pdf_canvas._expand_toc_overflow) — splicing continuation pages in
        # shifts numbering for everything after them, so the caption pass
        # runs again on the final, renumbered instances.
        instances = _expand_toc_overflow(instances, cfg, ctx, design)
        _collect_captions(instances, cfg, ctx)

        def rows(key):
            return [{"text": text, "page": page} for text, page in ctx.get(key) or []]

        return Response({
            "tables": rows("_table_captions"),
            "figures": rows("_figure_captions"),
            "images": rows("_image_captions"),
        })
