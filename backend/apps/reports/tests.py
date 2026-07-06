"""Reports tests: config merge, Arabic-aware PDF rendering, and API gating."""
import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, Permission, SeededRole
from apps.accounts.models import Company, Membership, Role, User
from apps.projects.models import Project

from .constants import default_config, merged_config
from .models import Report, ReportTemplate
from .pdf import build_report_pdf, has_arabic, shape

STRONG_PW = "Str0ngPassw0rd!"


def _sample_ctx():
    """A representative context with Arabic data, like a real construction report."""
    return {
        "report": {"title": "Monthly Progress Report", "number": "52",
                   "period_start": datetime.date(2026, 4, 1),
                   "period_finish": datetime.date(2026, 4, 30), "status": "Draft"},
        "project": {"name": "مشروع مدينة سانت كاترين", "code": "SCD-2026-001", "type": "Infrastructure",
                    "location": "Saint Catherine", "description": "وصف المشروع", "client": "NUCA",
                    "consultant": "Dar", "contractor": "Orascom", "planned_start": datetime.date(2025, 1, 1),
                    "planned_finish": datetime.date(2027, 1, 1), "revised_finish": None,
                    "size_sqm": None, "budget": None, "currency": "EGP", "notes": "ملاحظات"},
        "overall": 87.8,
        "breakdown": {"total": 100, "completed": 60, "in_progress": 30, "not_started": 10},
        "zones": [{"name": "المنطقة الأولى", "progress": 90.0}, {"name": "Zone B", "progress": 75.0}],
        "milestones": [{"title": "الأساسات", "date": datetime.date(2026, 3, 1), "status": "completed"}],
        "snapshots": [{"date": datetime.date(2026, 4, 1), "overall_progress": 85.0, "source": "tracker.xlsx"}],
    }


class ConfigTests(SimpleTestCase):
    def test_merged_config_fills_missing_keys(self):
        merged = merged_config({"colors": {"primary": "#ff0000"}})
        self.assertEqual(merged["colors"]["primary"], "#ff0000")  # override kept
        self.assertIn("table_header_bg", merged["colors"])         # default backfilled
        self.assertIn("summary", merged["sections"])

    def test_default_config_is_independent_copy(self):
        a = default_config()
        a["colors"]["primary"] = "#000000"
        self.assertNotEqual(default_config()["colors"]["primary"], "#000000")


class RichTextTests(SimpleTestCase):
    def test_sanitize_drops_scripts_and_unknown_tags(self):
        from .richtext import sanitize_html

        out = sanitize_html('<p>Hi</p><script>alert(1)</script><marquee>x</marquee>')
        self.assertNotIn("script", out)
        self.assertNotIn("alert(1)", out)   # script *contents* dropped too
        self.assertNotIn("marquee", out)    # unknown tag unwrapped
        self.assertIn("x", out)             # ...but its text kept
        self.assertIn("Hi", out)

    def test_sanitize_keeps_formatting_and_strips_handlers(self):
        from .richtext import sanitize_html

        out = sanitize_html('<p style="text-align:right" onclick="x()">'
                            '<b>bold</b> <font color="#c00000" size="5">red</font></p>')
        self.assertIn("<b>bold</b>", out)
        self.assertIn('color="#c00000"', out)
        self.assertNotIn("onclick", out)
        self.assertIn("text-align:right", out)

    def test_html_renders_to_flowables(self):
        from .richtext import html_to_flowables

        cfg = default_config()
        flow = html_to_flowables(
            '<ul><li>أولا</li><li><b>ثانيا</b></li></ul><div>Plain</div>', cfg, {})
        self.assertEqual(len(flow), 3)  # two list items + one paragraph


class PdfTests(SimpleTestCase):
    def test_arabic_detection_and_shaping(self):
        self.assertTrue(has_arabic("مشروع"))
        self.assertFalse(has_arabic("Project"))
        self.assertEqual(shape(None), "")
        self.assertTrue(shape("مشروع"))  # returns a non-empty reshaped string

    def test_builds_pdf_bytes_with_arabic_data(self):
        template = ReportTemplate(name="T", config=default_config())
        report = SimpleNamespace(title="Monthly Progress Report", template=template)
        data = build_report_pdf(report, _sample_ctx())
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 1000)

    def test_respects_section_toggles(self):
        cfg = default_config()
        cfg["sections"] = {k: False for k in cfg["sections"]}
        cfg["cover"]["enabled"] = False
        cfg["toc"]["enabled"] = False
        template = ReportTemplate(name="T", config=cfg)
        report = SimpleNamespace(title="Empty", template=template)
        # Still produces a valid (near-empty) document without error.
        self.assertTrue(build_report_pdf(report, _sample_ctx()).startswith(b"%PDF"))


class HierarchyRowsTests(TestCase):
    """`_hierarchy_rows` rolls up Project -> Zone -> Subzone (one level deeper
    than the existing zone table), using each scope's own dates when set."""

    def setUp(self):
        from apps.projects.models import Activity, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 12, 31))
        self.zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A")
        self.sub = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Building 1",
            parent=self.zone, planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 7, 1))
        Activity.objects.create(
            company=self.company, project=self.project, scope=self.sub,
            name="Task", weight=1, progress_percent=40)

    def test_rolls_up_zone_and_subzone_with_own_dates(self):
        from .services import _hierarchy_rows

        as_of = datetime.date(2026, 4, 1)  # 91/181 days into Building 1's own span
        rows = _hierarchy_rows(self.project, as_of=as_of)
        self.assertEqual(len(rows), 1)
        zone_row = rows[0]
        self.assertEqual(zone_row["name"], "Zone A")
        self.assertEqual(zone_row["actual"], 40.0)
        self.assertEqual(len(zone_row["children"]), 1)
        sub_row = zone_row["children"][0]
        self.assertEqual(sub_row["name"], "Building 1")
        self.assertEqual(sub_row["actual"], 40.0)
        self.assertAlmostEqual(sub_row["planned"], 49.7, delta=0.5)  # 90/181 days

    def test_uses_previous_scopes_map_when_given(self):
        from .services import _hierarchy_rows

        rows = _hierarchy_rows(self.project, prev_scopes={str(self.sub.id): 25.0})
        self.assertEqual(rows[0]["children"][0]["previous"], 25.0)
        self.assertIsNone(rows[0]["previous"])  # zone itself wasn't in the map


class DisciplineRowsTests(TestCase):
    """`_discipline_rows` splits one unit's progress by trade, using each
    activity's phase's discipline tag (a phase's direct parent is the unit)."""

    def setUp(self):
        from apps.projects.models import Activity, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)
        zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A")
        self.unit = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Building 1", parent=zone)
        concrete_phase = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="phase", name="Concrete works",
            parent=self.unit, discipline="concrete")
        electrical_phase = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="phase", name="Electrical works",
            parent=self.unit, discipline="electrical")
        untagged_phase = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="phase", name="Misc", parent=self.unit)
        Activity.objects.create(company=self.company, project=self.project, scope=concrete_phase,
                                name="Pour", weight=1, progress_percent=80)
        Activity.objects.create(company=self.company, project=self.project, scope=electrical_phase,
                                name="Wiring", weight=1, progress_percent=20)
        Activity.objects.create(company=self.company, project=self.project, scope=untagged_phase,
                                name="Other work", weight=1, progress_percent=100)

    def test_splits_progress_by_phase_discipline(self):
        from .services import _discipline_rows

        rows = _discipline_rows(self.project)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], "Building 1")
        self.assertEqual(row["concrete"], 80.0)
        self.assertEqual(row["electrical"], 20.0)
        self.assertIsNone(row["architecture"])
        self.assertIsNone(row["mechanical"])  # untagged phase's work isn't guessed into a column


class AreaDashboardsTests(TestCase):
    """`_area_dashboards` adds each zone's own duration (falling back to the
    project's) and recent subtree photos on top of the hierarchy rows."""

    def setUp(self):
        from apps.projects.models import Activity, ProgressEntry, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 12, 31))
        self.zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A",
            planned_start=datetime.date(2026, 2, 1), planned_finish=datetime.date(2026, 8, 1))
        activity = Activity.objects.create(
            company=self.company, project=self.project, scope=self.zone,
            name="Task", weight=1, progress_percent=50)
        entry = ProgressEntry.objects.create(
            company=self.company, project=self.project, activity=activity,
            date=datetime.date(2026, 4, 1), progress_percent=50)
        from apps.projects.models import ProgressImage
        ProgressImage.objects.create(company=self.company, entry=entry, caption="Pour")

    def test_uses_zone_dates_and_finds_subtree_photos(self):
        from .services import _area_dashboards, _hierarchy_rows

        as_of = datetime.date(2026, 5, 1)
        hierarchy = _hierarchy_rows(self.project, as_of=as_of)
        areas = _area_dashboards(self.project, hierarchy, as_of)
        self.assertEqual(len(areas), 1)
        area = areas[0]
        self.assertEqual(area["name"], "Zone A")
        self.assertEqual(area["duration"]["total"], 181)  # Zone A's own Feb-Aug span, not the project's
        self.assertEqual(len(area["photos"]), 1)
        self.assertEqual(area["photos"][0]["caption"], "Pour")

    def test_zone_without_own_dates_has_no_duration(self):
        """A dateless zone shows no duration pie (it would just repeat the
        project's numbers on every page); it still appears with its children."""
        from apps.projects.models import Activity, ProjectScope
        from .services import _area_dashboards, _hierarchy_rows

        dateless = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone B")
        unit = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Bldg", parent=dateless)
        Activity.objects.create(company=self.company, project=self.project, scope=unit,
                                name="W", weight=1, progress_percent=30)

        as_of = datetime.date(2026, 5, 1)
        hierarchy = _hierarchy_rows(self.project, as_of=as_of)
        areas = {a["name"]: a for a in _area_dashboards(self.project, hierarchy, as_of)}
        self.assertIsNone(areas["Zone B"]["duration"])      # dateless -> no pie
        self.assertIsNotNone(areas["Zone A"]["duration"])   # has own dates -> kept


class GanttRowsTests(TestCase):
    """`_gantt_rows` builds zone+child Gantt bars from each scope's OWN dates
    (no project-date fallback, since every bar would otherwise be identical)."""

    def setUp(self):
        from apps.projects.models import Activity, ProjectScope

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL,
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 12, 31))
        self.zone = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="zone", name="Zone A",
            planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 6, 1))
        self.dated_child = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Building 1",
            parent=self.zone, planned_start=datetime.date(2026, 1, 1), planned_finish=datetime.date(2026, 3, 1),
            revised_finish=datetime.date(2026, 4, 1))
        self.undated_child = ProjectScope.objects.create(
            company=self.company, project=self.project, scope_type="area", name="Building 2", parent=self.zone)
        Activity.objects.create(
            company=self.company, project=self.project, scope=self.dated_child,
            name="Task", weight=1, progress_percent=50)
        Activity.objects.create(
            company=self.company, project=self.project, scope=self.undated_child,
            name="Task 2", weight=1, progress_percent=100)

    def test_omits_scopes_without_own_dates(self):
        from .services import _gantt_rows

        rows = _gantt_rows(self.project)
        names = [r["name"] for r in rows]
        self.assertIn("Zone A", names)        # has its own dates
        self.assertIn("Building 1", names)    # has its own dates
        self.assertNotIn("Building 2", names)  # no dates -> omitted

    def test_rolls_up_progress_and_keeps_revised_finish(self):
        from .services import _gantt_rows

        rows = _gantt_rows(self.project)
        child = next(r for r in rows if r["name"] == "Building 1")
        self.assertEqual(child["level"], 1)
        self.assertEqual(child["progress"], 50.0)
        self.assertEqual(child["revised_finish"], datetime.date(2026, 4, 1))

        zone_row = next(r for r in rows if r["name"] == "Zone A")
        self.assertEqual(zone_row["level"], 0)
        # Zone's own weight (0) + child's weight(1)*50 + untracked child's weight(1)*100 -> 75 overall
        self.assertEqual(zone_row["progress"], 75.0)


class FinanceReportTests(TestCase):
    """Cash flow, invoices and submittals flow into the report context and PDF."""

    def setUp(self):
        from apps.projects.models import CashFlowEntry, Invoice, Submittal

        self.company = Company.objects.create(name="Acme")
        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL, currency="EGP")
        CashFlowEntry.objects.create(company=self.company, project=self.project,
                                     month=datetime.date(2026, 1, 1), planned=100, actual=80)
        CashFlowEntry.objects.create(company=self.company, project=self.project,
                                     month=datetime.date(2026, 2, 1), planned=200, actual=150)
        Invoice.objects.create(company=self.company, project=self.project, name="Extract 1", value=1500)
        Invoice.objects.create(company=self.company, project=self.project, name="Extract 2", value=2500)
        Submittal.objects.create(company=self.company, project=self.project, title="Rebar shop dwg",
                                 submittal_type="shop_drawing", discipline="concrete", status="approved")
        Submittal.objects.create(company=self.company, project=self.project, title="Paint sample",
                                 submittal_type="material", discipline="architecture", status="pending")

    def test_context_aggregates_finances(self):
        from .services import build_report_context

        rep = Report.objects.create(company=self.company, project=self.project, title="M", report_number="1")
        ctx = build_report_context(rep)
        self.assertEqual(len(ctx["cashflow"]), 2)
        self.assertEqual(ctx["cashflow"][1]["cum_actual"], 230.0)  # 80 + 150
        self.assertEqual(ctx["invoices_total"], 4000.0)
        self.assertEqual(len(ctx["submittals"]["rows"]), 2)
        approved = next(s for s in ctx["submittals"]["summary"] if s["key"] == "approved")
        self.assertEqual(approved["count"], 1)

    def test_pdf_renders_with_finance_sections(self):
        from .services import build_report_context

        rep = Report.objects.create(company=self.company, project=self.project, title="Monthly", report_number="1")
        ctx = build_report_context(rep)
        rep.template = ReportTemplate(name="T", config=default_config())
        data = build_report_pdf(rep, ctx)
        self.assertTrue(data.startswith(b"%PDF"))


class ReportsApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        admin_role = Role.objects.create(
            company=self.company, name=SeededRole.COMPANY_ADMIN, permissions=COMPANY_ADMIN_PERMISSIONS)
        self.admin = User.objects.create_user(email="admin@acme.com", password=STRONG_PW, company=self.company)
        Membership.objects.create(company=self.company, user=self.admin, role=admin_role)

        viewer_role = Role.objects.create(
            company=self.company, name="Viewer", permissions=[Permission.VIEW_PROJECTS.value])
        self.viewer = User.objects.create_user(email="viewer@acme.com", password=STRONG_PW, company=self.company)
        Membership.objects.create(company=self.company, user=self.viewer, role=viewer_role)

        self.project = Project.objects.create(
            company=self.company, name="Tower", project_type=Project.ProjectType.COMMERCIAL)
        self.client = APIClient()

    def test_viewer_cannot_create_template(self):
        self.client.force_authenticate(self.viewer)
        res = self.client.post("/api/report-templates/", {"name": "X"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_admin_creates_template_with_default_config(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post("/api/report-templates/", {"name": "Standard"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertIn("colors", res.data["config"])

    def test_report_create_and_pdf_download(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            "/api/reports/",
            {"project": str(self.project.id), "title": "Monthly", "report_number": "1"},
            format="json")
        self.assertEqual(res.status_code, 201)
        report_id = res.data["id"]

        pdf = self.client.get(f"/api/reports/{report_id}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(pdf.streaming_content if hasattr(pdf, "streaming_content") else [pdf.content]).startswith(b"%PDF"))

    def _progress_image(self, caption, when):
        import datetime as _dt

        from apps.projects.models import Activity, ProgressEntry, ProgressImage, ProjectScope
        zone = ProjectScope.objects.create(company=self.company, project=self.project, scope_type="zone", name="Z")
        act = Activity.objects.create(company=self.company, project=self.project, scope=zone, name="Pour", weight=1)
        entry = ProgressEntry.objects.create(
            company=self.company, project=self.project, activity=act,
            date=_dt.date.fromisoformat(when), progress_percent=50)
        return ProgressImage.objects.create(company=self.company, entry=entry, caption=caption)

    def test_progress_image_picker_select_and_orders_by_date(self):
        # Two schedule photos on different dates; the report should render them
        # earliest-first once selected.
        later = self._progress_image("Later", "2026-03-01")
        earlier = self._progress_image("Earlier", "2026-01-01")
        report = Report.objects.create(company=self.company, project=self.project, title="R")

        self.client.force_authenticate(self.admin)
        listing = self.client.get(f"/api/reports/{report.id}/progress-images/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([p["caption"] for p in listing.data], ["Earlier", "Later"])  # date asc
        self.assertFalse(any(p["selected"] for p in listing.data))

        # Select both (in reverse order) — persisted, then re-sorted by date in PDF.
        put = self.client.put(f"/api/reports/{report.id}/progress-images/",
                              {"selected_ids": [str(later.id), str(earlier.id)]}, format="json")
        self.assertEqual(put.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(set(report.progress_image_ids), {str(later.id), str(earlier.id)})

        from .services import build_report_context
        photos = build_report_context(report)["photos"]
        self.assertEqual([p["caption"] for p in photos], ["Earlier", "Later"])  # earliest first

    def test_progress_image_picker_write_needs_export_perm(self):
        report = Report.objects.create(company=self.company, project=self.project, title="R")
        self.client.force_authenticate(self.viewer)  # VIEW_PROJECTS only
        self.assertEqual(self.client.get(f"/api/reports/{report.id}/progress-images/").status_code, 200)
        put = self.client.put(f"/api/reports/{report.id}/progress-images/",
                              {"selected_ids": []}, format="json")
        self.assertEqual(put.status_code, 403)

    def test_progress_image_picker_rejects_foreign_ids(self):
        report = Report.objects.create(company=self.company, project=self.project, title="R")
        self.client.force_authenticate(self.admin)
        put = self.client.put(f"/api/reports/{report.id}/progress-images/",
                              {"selected_ids": ["not-a-uuid", str(self.project.id)]}, format="json")
        self.assertEqual(put.status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.progress_image_ids, [])  # junk + non-progress IDs dropped

    def test_tenant_isolation_on_reports(self):
        other = Company.objects.create(name="Other")
        other_user = User.objects.create_user(email="o@other.com", password=STRONG_PW, company=other)
        role = Role.objects.create(company=other, name="A", permissions=[Permission.EXPORT_REPORTS.value])
        Membership.objects.create(company=other, user=other_user, role=role)
        Report.objects.create(company=self.company, project=self.project, title="Mine")

        self.client.force_authenticate(other_user)
        res = self.client.get("/api/reports/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 0)  # can't see Acme's report
