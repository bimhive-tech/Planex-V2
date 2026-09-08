"""Tests for the Planex Code P6 parser (p6_id_schedule_import.py).

Built against the team's first real export (Mansoura 6 - Building, Aug
2026) — see that module's docstring for the empirically-confirmed shape.
"""
import datetime
import io

import openpyxl
from django.test import SimpleTestCase, TestCase

from apps.accounts.models import Company

from .imports import import_workbook
from .models import Activity, Project, ProjectScope
from .p6_id_schedule_import import is_milestone_code, milestone_scope_path, segment_path


class SegmentPathTests(TestCase):
    def test_real_file_shape_ten_segments_two_dropped(self):
        """The team's actual export: 10 dash-separated segments (not the
        legend's full 12 — Level and Sub-discipline are dropped entirely),
        with Area/Sub-area/Part kept as a literal "0" placeholder."""
        path = segment_path("MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-1")
        self.assertEqual(path, ["PH1", "Z(A)", "Building 6", "Internal Finishes"])

    def test_bare_tag_word_is_a_placeholder(self):
        # "CON" alone (no distinguishing suffix) means "this project doesn't
        # branch on Construction" — same as "0" for Area/Sub-area/Part.
        path = segment_path("MN(6)-CON-0-0-PH2-Z(B)-0-Building 12-Stairs-30")
        self.assertEqual(path, ["PH2", "Z(B)", "Building 12", "Stairs"])

    def test_project_code_and_differentiator_are_dropped(self):
        # First segment (project code) and last (per-row differentiator) are
        # never part of the tree path — the real Activity ID is used as the
        # leaf's own code instead of the differentiator.
        path = segment_path("PN01-PH1-1")
        self.assertEqual(path, ["PH1"])

    def test_all_placeholders_returns_empty(self):
        self.assertEqual(segment_path("MN(6)-CON-0-0-0-0-0-0-DEC-1"), [])

    def test_too_few_segments_returns_empty(self):
        self.assertEqual(segment_path("MN(6)-1"), [])
        self.assertEqual(segment_path("not a code"), [])

    def test_non_string_returns_empty(self):
        self.assertEqual(segment_path(None), [])
        self.assertEqual(segment_path(123), [])


class MilestoneCodeTests(TestCase):
    def test_bare_project_wide_milestone_code(self):
        self.assertTrue(is_milestone_code("MN(6)-MS-1"))
        self.assertEqual(milestone_scope_path("MN(6)-MS-1"), ())

    def test_building_tied_milestone_code(self):
        code = "MN(6)-MS-PH1-Z(A)-Building 15-1"
        self.assertTrue(is_milestone_code(code))
        self.assertEqual(milestone_scope_path(code), ("PH1", "Z(A)", "Building 15"))

    def test_discipline_code_is_not_a_milestone_code(self):
        self.assertFalse(is_milestone_code("MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-1"))

    def test_non_string_is_not_a_milestone_code(self):
        self.assertFalse(is_milestone_code(None))
        self.assertFalse(is_milestone_code(123))


class IdScheduleImportTests(TestCase):
    """Same header shape as the reference P6 schedule export, plus a
    separate "Planex Code" column — Activity ID/Name stay the leaf
    activity's own identity; Planex Code only drives the WBS tree."""

    HEADER = ["Planex Code", "Activity ID", "Activity Name", "Original Duration", "Start", "Finish",
              "Activity % Complete", "Budgeted Total Cost", "Earned Value Cost"]

    def _workbook(self, rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(self.HEADER)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_builds_tree_from_real_file_shaped_codes(self):
        d = datetime.date
        rows = [
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-1", "MN6-A6-01-01", "Seal",
             10, d(2026, 1, 1), d(2026, 1, 10), 0.5, 1000, 500],
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-2", "MN6-A6-01-02", "Putty",
             5, d(2026, 1, 11), d(2026, 1, 15), 0, 500, 0],
            # A second discipline under the same Building.
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Stairs-1", "MN6-A6-02-01", "Stair render",
             8, d(2026, 2, 1), d(2026, 2, 8), 1, 2000, 2000],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")

        result = import_workbook(project, self._workbook(rows), source="planex_code.xlsx")
        self.assertEqual(result["source_kind"], "p6_schedule")
        self.assertEqual(result["activities"], 3)

        stage = ProjectScope.objects.get(project=project, name="PH1")
        self.assertEqual(stage.scope_type, ProjectScope.ScopeType.STAGE)
        self.assertEqual(stage.parent, None)

        zone = ProjectScope.objects.get(project=project, name="Z(A)")
        self.assertEqual(zone.scope_type, ProjectScope.ScopeType.ZONE)
        self.assertEqual(zone.parent, stage)

        building = ProjectScope.objects.get(project=project, name="Building 6")
        self.assertEqual(building.scope_type, ProjectScope.ScopeType.AREA)
        self.assertEqual(building.parent, zone)

        disciplines = list(ProjectScope.objects.filter(project=project, parent=building).order_by("name"))
        self.assertEqual([s.name for s in disciplines], ["Internal Finishes", "Stairs"])
        self.assertEqual(disciplines[0].scope_type, ProjectScope.ScopeType.PHASE)

        # The real Activity ID is used as the leaf's own code — not a
        # synthetic differentiator like the old assumed scheme's "NU001".
        seal = Activity.objects.get(project=project, code="MN6-A6-01-01")
        self.assertEqual(seal.name, "Seal")
        self.assertEqual(float(seal.progress_percent), 50.0)

        # Group nodes carry no Start/Finish of their own — rolled up from activities.
        self.assertEqual(stage.planned_start, d(2026, 1, 1))
        self.assertEqual(stage.planned_finish, d(2026, 2, 8))

    def test_reads_baseline_actual_duration_spi_and_schedule_variance(self):
        """Four columns the real export carries but nothing used to read:
        "BL Project Duration", "Actual Duration", "Schedule Performance
        Index", "Schedule Variance" — now captured on the Activity."""
        d = datetime.date
        header = ["Planex Code", "Activity ID", "Activity Name", "BL Project Duration",
                  "Original Duration", "Actual Duration", "Remaining Duration", "Start", "Finish",
                  "Total Float", "Activity % Complete", "Performance % Complete", "Schedule % Complete",
                  "Schedule Performance Index", "Budgeted Total Cost", "Earned Value Cost", "Schedule Variance"]
        rows = [
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-1", "MN6-A6-01-01", "Seal",
             12, 12, 12, 0, d(2026, 1, 1), d(2026, 1, 10), None, 1, 1, 1, 1.02, 1000, 998, -2.5],
        ]
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(header)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        import_workbook(project, buf, source="planex_code.xlsx")

        seal = Activity.objects.get(project=project, code="MN6-A6-01-01")
        self.assertEqual(seal.baseline_duration, 12)
        self.assertEqual(seal.actual_duration, 12)
        self.assertAlmostEqual(float(seal.schedule_performance_index), 1.02)
        self.assertAlmostEqual(float(seal.schedule_variance), -2.5)

    def test_scope_label_read_from_the_wbs_heading_text(self):
        """Alongside its own code segment, the file's real WBS heading rows
        (interleaved with the coded leaf rows, indentation-based, the same
        as the old parser reads) carry a human-readable name. Each scope
        node should pick that up as `label`, keeping `name` as the stable
        code used for matching — a naming change or a missing heading on a
        later import must never affect `name`, only cosmetically update
        `label` (or leave it blank)."""
        d = datetime.date
        rows = [
            [None, "Mansora 6 - Revised Final", None, 0, None, None, None, 0, 0],
            # The "CON" tag's own WBS heading — real in the file, but dropped
            # from the code path as a placeholder (see segment_path). Sits at
            # the front, so it must not shift the backward alignment of the
            # levels that DO have a code counterpart.
            [None, "  Execution Phase", None, 0, None, None, None, 0, 0],
            [None, "    المرحلة الاولي (75 عمارة)", None, 0, None, None, None, 0, 0],
            [None, "      Zone (A)", None, 0, None, None, None, 0, 0],
            [None, "        (A6) Building", None, 0, None, None, None, 0, 0],
            [None, "          التشطيب الداخلي", None, 0, None, None, None, 0, 0],
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-1", "A1", "Seal",
             1, d(2026, 1, 1), d(2026, 1, 2), 1, 1000, 1000],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        import_workbook(project, self._workbook(rows), source="planex_code.xlsx")

        phase = ProjectScope.objects.get(project=project, name="PH1")
        self.assertEqual(phase.label, "المرحلة الاولي (75 عمارة)")

        zone = ProjectScope.objects.get(project=project, name="Z(A)")
        self.assertEqual(zone.label, "Zone (A)")

        building = ProjectScope.objects.get(project=project, name="Building 6")
        self.assertEqual(building.label, "(A6) Building")

        discipline = ProjectScope.objects.get(project=project, name="Internal Finishes")
        self.assertEqual(discipline.label, "التشطيب الداخلي")

    def test_scope_label_blank_when_no_wbs_heading_rows_exist(self):
        """A file with only coded leaf rows and no separate WBS heading rows
        (the shape every other test in this file uses) must import exactly
        as before — `label` stays blank, `name` (the code) is what's used,
        no crash from a missing heading stack entry."""
        d = datetime.date
        rows = [
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-1", "A1", "Seal",
             1, d(2026, 1, 1), d(2026, 1, 2), 1, 1000, 1000],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        import_workbook(project, self._workbook(rows), source="planex_code.xlsx")
        phase = ProjectScope.objects.get(project=project, name="PH1")
        self.assertEqual(phase.label, "")

    def test_budgeted_total_cost_header_drives_weighting(self):
        """This file's cost column is named "Budgeted Total Cost", not the
        original template's "Budgeted Material Cost" — must still be read
        for cost-based roll-up weighting."""
        d = datetime.date
        rows = [
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 1-ELEC-1", "A1", "Big", 1,
             d(2026, 1, 1), d(2026, 1, 2), 1, 9000, 9000],
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 1-ELEC-2", "A2", "Small", 1,
             d(2026, 1, 1), d(2026, 1, 2), 0, 1000, 0],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        result = import_workbook(project, self._workbook(rows), source="planex_code.xlsx")
        self.assertEqual(result["weighted_by"], "budget")

    def test_bare_tag_placeholders_all_the_way_falls_back_to_uncategorized(self):
        d = datetime.date
        rows = [
            ["MN(6)-CON-0-0-0-0-0-0-DEC-1", "A1", "Orphan task",
             1, d(2026, 1, 1), d(2026, 1, 2), 0, 0, 0],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        import_workbook(project, self._workbook(rows), source="planex_code.xlsx")

        # Every middle segment is a placeholder ("0" or "DEC" alone) -> no
        # real tree path -> this parser doesn't match the row at all, so
        # detection falls through (no Planex Code sheet actually matched).
        self.assertFalse(ProjectScope.objects.filter(project=project).exists())

    def test_key_milestones_branch_has_no_planex_code_but_still_imports(self):
        """A real P6 export keeps its key dates (project start/finish,
        handover milestones) as zero-work activities under one WBS heading
        — carrying NO Planex Code at all, since they aren't coded discipline
        work. The code-driven walk must not just silently drop them; they
        belong in the Milestones panel, same as the old indentation
        parser's own milestone branch."""
        d = datetime.date
        rows = [
            # Planex-Code-driven real work, so the sheet is detected at all.
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 1-ELEC-1", "A1", "Wiring",
             1, d(2026, 1, 1), d(2026, 1, 2), 1, 1000, 1000],
            # The milestone WBS branch — no Planex Code on any of these rows.
            [None, "  Key Milestones", None, 0, d(2026, 1, 1), d(2026, 12, 1), None, 0, 0],
            [None, "MS-START", "Project start", 0, d(2026, 1, 1), None, 1, 0, 0],
            [None, "MS-END", "Project end", 0, None, d(2026, 12, 1), 0, 0, 0],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        result = import_workbook(project, self._workbook(rows), source="planex_code.xlsx")

        self.assertEqual(result["activities"], 1)  # only the coded row
        self.assertEqual(result["milestones"], 2)
        from .models import Milestone
        titles = set(Milestone.objects.filter(project=project).values_list("title", flat=True))
        self.assertEqual(titles, {"Project start", "Project end"})
        start_ms = Milestone.objects.get(project=project, title="Project start")
        self.assertEqual(start_ms.status, Milestone.Status.COMPLETED)  # pct=1 -> 100%
        self.assertEqual(start_ms.progress_percent, 100)
        end_ms = Milestone.objects.get(project=project, title="Project end")
        self.assertEqual(end_ms.status, Milestone.Status.UPCOMING)  # pct=0
        # A real 0% (not missing) must still be stored, not left null.
        self.assertEqual(end_ms.progress_percent, 0)

        # The milestone branch must not also appear as a schedule scope.
        self.assertFalse(ProjectScope.objects.filter(project=project, name="Key Milestones").exists())

    def test_milestone_with_no_pct_column_value_stores_null_not_zero(self):
        """A milestone row with nothing at all in the "Activity % Complete"
        column must store progress_percent=None — never silently coerced to
        0, which would be indistinguishable from a real "0% complete"."""
        d = datetime.date
        rows = [
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 1-ELEC-1", "A1", "Wiring",
             1, d(2026, 1, 1), d(2026, 1, 2), 1, 1000, 1000],
            [None, "  Key Milestones", None, 0, d(2026, 1, 1), d(2026, 12, 1), None, 0, 0],
            [None, "MS-START", "Project start", 0, d(2026, 1, 1), None, None, 0, 0],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        import_workbook(project, self._workbook(rows), source="planex_code.xlsx")
        from .models import Milestone
        ms = Milestone.objects.get(project=project, title="Project start")
        self.assertIsNone(ms.progress_percent)
        self.assertEqual(ms.status, Milestone.Status.UPCOMING)  # still defaults sensibly

    def test_ms_coded_milestone_resolves_scope_to_the_matching_building(self):
        """The agreed convention for once the team codes the Key Milestones
        branch: "MS" as the 2nd segment, with the same zone/building
        segments as the discipline rows when the milestone is tied to one
        building. It should resolve to the SAME ProjectScope the discipline
        rows created — not a raw-text match, a real FK."""
        d = datetime.date
        rows = [
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 1-ELEC-1", "A1", "Wiring",
             1, d(2026, 1, 1), d(2026, 1, 2), 1, 1000, 1000],
            # Tied to that same building — should resolve to its scope.
            ["MN(6)-MS-PH1-Z(A)-Building 1-1", "MS1", "(A1) Building handover",
             0, None, d(2026, 3, 1), 1, 0, 0],
            # Project-wide — no zone/building segments, scope stays null.
            ["MN(6)-MS-2", "MS2", "Project start",
             0, d(2026, 1, 1), None, 1, 0, 0],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        result = import_workbook(project, self._workbook(rows), source="planex_code.xlsx")

        self.assertEqual(result["activities"], 1)
        self.assertEqual(result["milestones"], 2)

        from .models import Milestone
        building = ProjectScope.objects.get(project=project, name="Building 1")
        handover = Milestone.objects.get(project=project, title="(A1) Building handover")
        self.assertEqual(handover.scope_id, building.id)
        self.assertEqual(handover.status, Milestone.Status.COMPLETED)

        project_start = Milestone.objects.get(project=project, title="Project start")
        self.assertIsNone(project_start.scope_id)

    def test_ms_coded_milestones_take_priority_over_indentation_fallback(self):
        """When the sheet has real MS-coded milestone rows, use those instead
        of the indentation/keyword fallback — even if a WBS heading elsewhere
        happens to look milestone-ish, it should be ignored in favor of the
        explicit code."""
        d = datetime.date
        rows = [
            ["MN(6)-CON-0-0-PH1-Z(A)-0-Building 1-ELEC-1", "A1", "Wiring",
             1, d(2026, 1, 1), d(2026, 1, 2), 1, 1000, 1000],
            ["MN(6)-MS-1", "MS1", "Project start",
             0, d(2026, 1, 1), None, 1, 0, 0],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        result = import_workbook(project, self._workbook(rows), source="planex_code.xlsx")
        self.assertEqual(result["milestones"], 1)
        from .models import Milestone
        self.assertEqual(
            set(Milestone.objects.filter(project=project).values_list("title", flat=True)),
            {"Project start"},
        )

    def test_no_planex_code_column_falls_through_to_old_parser(self):
        """A file with no "Planex Code" column at all (the previous
        template shape) must still import via the leading-space scheme,
        completely unaffected by this module."""
        d = datetime.date
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Activity ID", "Activity Name", "Original Duration", "Start", "Finish",
                  "Activity % Complete", "Budgeted Material Cost", "Earned Value Cost"])
        ws.append(["  Construction Phase", None, 0, d(2026, 1, 1), d(2026, 2, 1), None, 0, 0])
        ws.append(["CN.01", "Foundation", 10, d(2026, 1, 1), d(2026, 1, 10), 0.5, 1000, 500])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        result = import_workbook(project, buf, source="legacy.xlsx")
        self.assertEqual(result["source_kind"], "p6_schedule")
        self.assertTrue(ProjectScope.objects.filter(project=project, name="Construction Phase").exists())


class ScheduleCompletePlannedTests(TestCase):
    """P6's "Schedule % Complete" is the BASELINE's own view of how far along
    the work should be — the figure the client's reports quote as planned
    ("cumulative Plan Performance%"). It must be read from the file rather than
    re-derived from Start/Finish, which are the CURRENT schedule and have
    already absorbed every delay (reported 2026-09-02)."""

    HEADER = ["Planex Code", "Activity ID", "Activity Name", "BL Project Duration",
              "Original Duration", "Actual Duration", "Remaining Duration", "Start", "Finish",
              "Total Float", "Activity % Complete", "Performance % Complete", "Schedule % Complete",
              "Schedule Performance Index", "Budgeted Total Cost", "Earned Value Cost",
              "Schedule Variance"]

    def _book(self, rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(self.HEADER)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def _row(self, code, activity_id, name, sched_pct, cost, pct=0.5):
        d = datetime.date
        # Start/Finish deliberately run well past the as-of date: a date-based
        # planned estimate would read far below 100% here, which is the bug.
        return [code, activity_id, name, 12, 12, 6, 6, d(2026, 1, 1), d(2030, 1, 1),
                None, pct, pct, sched_pct, 1.0, cost, 0, 0]

    def _import(self, rows):
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        import_workbook(project, self._book(rows), source="planex_code.xlsx")
        return project

    def test_schedule_percent_is_captured_on_the_activity(self):
        project = self._import([
            self._row("MN(6)-CON-0-0-PH1-Z(A)-0-B6-Finishes-1", "A-1", "Seal", 1, 1000),
        ])
        self.assertEqual(float(Activity.objects.get(project=project, code="A-1").schedule_percent), 100.0)

    def test_scope_planned_map_rolls_up_weighted_by_cost(self):
        """A zone's planned % is the cost-weighted mean of its activities', the
        same rollup scope_progress_map does for actual progress."""
        from .services import scope_planned_map

        project = self._import([
            self._row("MN(6)-CON-0-0-PH1-Z(A)-0-B6-Finishes-1", "A-1", "Cheap", 1, 1000),
            self._row("MN(6)-CON-0-0-PH1-Z(A)-0-B6-Finishes-2", "A-2", "Dear", 0.5, 3000),
        ])
        zone = ProjectScope.objects.get(project=project, name="Z(A)")
        # (1000 x 100% + 3000 x 50%) / 4000
        self.assertEqual(scope_planned_map(project)[str(zone.id)], 62.5)

    def test_planned_comes_from_the_baseline_not_elapsed_time(self):
        """The regression this exists for: every activity's baseline says 100%
        while the live schedule runs to 2030, so a date-based estimate would
        report a fraction. The report must quote 100%."""
        from apps.reports.services import _scope_planned_progress
        from .services import scope_planned_map

        project = self._import([
            self._row("MN(6)-CON-0-0-PH1-Z(A)-0-B6-Finishes-1", "A-1", "Seal", 1, 1000),
        ])
        zone = ProjectScope.objects.get(project=project, name="Z(A)")
        as_of = datetime.date(2026, 6, 1)
        self.assertEqual(_scope_planned_progress(zone, project, as_of, scope_planned_map(project)), 100.0)
        # Without the map it falls back to elapsed time, which is the old,
        # wrong answer — kept only for sources carrying no such column.
        self.assertLess(_scope_planned_progress(zone, project, as_of), 100.0)

    def test_project_planned_falls_back_to_the_weighted_activities(self):
        """The Planex-code tree is built from the code column, so the project
        title row never becomes a root and can't supply the project figure."""
        project = self._import([
            self._row("MN(6)-CON-0-0-PH1-Z(A)-0-B6-Finishes-1", "A-1", "Cheap", 1, 1000),
            self._row("MN(6)-CON-0-0-PH1-Z(A)-0-B6-Finishes-2", "A-2", "Dear", 0.5, 3000),
        ])
        project.refresh_from_db()
        self.assertEqual(float(project.imported_planned_progress_percent), 62.5)

    def test_a_source_without_the_column_is_unchanged(self):
        """Zone trackers and older exports carry no Schedule % Complete; they
        must keep their date-based estimate rather than losing planned %."""
        from .services import scope_planned_map

        rows = [self._row("MN(6)-CON-0-0-PH1-Z(A)-0-B6-Finishes-1", "A-1", "Seal", None, 1000)]
        project = self._import(rows)
        self.assertIsNone(Activity.objects.get(project=project, code="A-1").schedule_percent)
        self.assertEqual(scope_planned_map(project), {})


class PlanexCodeLegendTests(SimpleTestCase):
    """A Planex Code's meaning comes from WHICH legend slot a segment sits in.
    Every slot a file fills becomes its own level of the tree.

    Cairo Airport is coded purely by part/level/discipline — every area, phase
    and zone slot is "0" — so collapsing the zeros promoted "Civil" (a
    discipline, slot 10) to the first surviving position and the tree typed it
    as a stage, with levels and work packages landing in the zone and area
    slots under it (reported 2026-09-07).
    """

    LEGEND = ["PN", "CON", "AR", "SUB AR", "PH", "Z", "P", "U", "LEV", "DEC", "SUB DEC", "NU"]

    def test_every_slot_keeps_its_own_level(self):
        from .p6_id_schedule_import import slot_path

        self.assertEqual(
            slot_path("CA-CON-0-0-0-0-P1-0-L.2A-MEP-Electrical Works-358", self.LEGEND),
            [("P1", "part"), ("L.2A", "level"), ("MEP", "discipline"),
             ("Electrical Works", "sub_discipline")],
        )

    def test_a_slot_means_the_same_thing_with_or_without_its_neighbours(self):
        """The whole point: "L.2" is a Level whether or not the row also names
        a Part, and "Civil" is a Discipline wherever it appears. Read
        positionally it was a zone on one row and a stage on the next."""
        from .p6_id_schedule_import import slot_path

        self.assertEqual(slot_path("CA-CON-0-0-0-0-0-0-L.2-Civil-Block works-120", self.LEGEND),
                         [("L.2", "level"), ("Civil", "discipline"), ("Block works", "sub_discipline")])
        self.assertEqual(slot_path("CA-CON-0-0-0-0-0-0-0-Civil-Pre Demolitioning-1", self.LEGEND),
                         [("Civil", "discipline"), ("Pre Demolitioning", "sub_discipline")])

    def test_a_discipline_with_no_sub_discipline_stands_alone(self):
        from .p6_id_schedule_import import slot_path

        self.assertEqual(slot_path("CA-CON-0-0-0-0-0-0-0-Landscape-0-628", self.LEGEND),
                         [("Landscape", "discipline")])

    def test_the_legends_own_order_is_the_nesting_order(self):
        from .p6_id_schedule_import import slot_path

        self.assertEqual(
            slot_path("XX-CON-Area 1-Sub 2-PH2-Z(C)-0-Unit 4-0-MEP-0-7", self.LEGEND),
            [("Area 1", "area"), ("Sub 2", "sub_area"), ("PH2", "stage"),
             ("Z(C)", "zone"), ("Unit 4", "unit"), ("MEP", "discipline")],
        )

    def test_a_code_that_does_not_fill_the_legend_is_left_alone(self):
        """Mansoura carries 10 segments against the same 12-slot legend, so
        which two are missing is unknowable — it keeps the positional
        reading rather than being silently misaligned by two places."""
        from .p6_id_schedule_import import segment_path, slot_path

        code = "MN(6)-CON-0-0-PH1-Z(A)-0-Building 6-Internal Finishes-1"
        self.assertEqual(slot_path(code, self.LEGEND), [])
        self.assertEqual(segment_path(code), ["PH1", "Z(A)", "Building 6", "Internal Finishes"])

    def test_no_legend_means_no_change(self):
        from .p6_id_schedule_import import slot_path

        self.assertEqual(slot_path("CA-CON-0-0-0-0-0-0-0-Civil-Pre Demolitioning-1", []), [])


class LegendReadImportTests(TestCase):
    """End-to-end for a file that fills every slot its legend declares.

    Cairo Airport codes its work by part/level/discipline and leaves every
    area, phase and zone slot "0". Read positionally that promoted "Civil" to
    the first surviving segment, so the report showed disciplines as stages
    and work packages as zones: "Civil Works" as a stage, "Steel Works" as a
    zone (reported 2026-09-07)."""

    HEADER = ["Planex Code", "Activity ID", "Activity Name", "Original Duration", "Start", "Finish",
              "Activity % Complete", "Budgeted Total Cost", "Earned Value Cost"]
    LEGEND = ["PN", "CON", "AR", "SUB AR", "PH", "Z", "P", "U", "LEV", "DEC", "SUB DEC", "NU"]

    def _workbook(self, rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "p6"
        ws.append(self.HEADER)
        for row in rows:
            ws.append(row)
        legend = wb.create_sheet("Planex Code")
        legend.append(["CODE", *self.LEGEND])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def _import(self):
        d = datetime.date

        def head(indent, text):
            return ["", " " * indent + text, None, None, None, None, None, None, None]

        def act(code, aid, name):
            return [code, aid, name, 5, d(2026, 1, 1), d(2026, 1, 10), 0.5, 1000, 500]

        # The WBS nests discipline > sub-discipline > level > part, the
        # REVERSE of the order the legend declares those slots in — the real
        # file's shape.
        rows = [
            head(2, "Civil Works"),
            head(4, "Steel Works"),
            head(6, "Level 2"),
            head(8, "Part 1"),
            act("CA-CON-0-0-0-0-P1-0-L.2-Civil-Steel Works-80", "PR1430", "Install columns"),
            head(8, "Part 2"),
            act("CA-CON-0-0-0-0-P2-0-L.2-Civil-Steel Works-81", "PR1431", "Install beams"),
            head(6, "Level 2A"),
            act("CA-CON-0-0-0-0-0-0-L.2A-Civil-Steel Works-82", "PR1432", "Deck"),
            head(4, "Pre-Demolishing"),
            act("CA-CON-0-0-0-0-0-0-0-Civil-Pre Demolitioning-1", "PR4190", "Metal fence"),
            head(2, "MEP Works"),
            head(4, "Electrical Works"),
            head(6, "Level 2A"),
            act("CA-CON-0-0-0-0-P2-0-L.2A-MEP-Electrical Works-358", "PR2000", "Conduits"),
            head(6, "Level 2"),
            act("CA-CON-0-0-0-0-P1-0-L.2-MEP-Electrical Works-359", "PR2001", "Trays"),
            head(4, "Plumbing Works"),
            act("CA-CON-0-0-0-0-0-0-L.2-MEP-Plumbing-360", "PR2002", "Pipes"),
            # Discipline with no sub-discipline — the discipline IS the work.
            head(2, "Landscape Works"),
            act("CA-CON-0-0-0-0-0-0-0-Landscape-0-628", "PR6000", "Planting"),
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Airport", project_type="infrastructure")
        import_workbook(project, self._workbook(rows), source="cairo.xlsx")
        return project

    def test_places_become_places_and_work_packages_become_phases(self):
        project = self._import()
        by_type = {}
        for s in ProjectScope.objects.filter(project=project):
            by_type.setdefault(s.scope_type, set()).add(s.name)
        self.assertEqual(by_type.get(ProjectScope.ScopeType.PART), {"P1", "P2"})
        self.assertEqual(by_type.get(ProjectScope.ScopeType.LEVEL), {"L.2", "L.2A"})
        self.assertEqual(by_type.get(ProjectScope.ScopeType.DISCIPLINE),
                         {"Civil", "MEP", "Landscape"})
        self.assertEqual(by_type.get(ProjectScope.ScopeType.SUB_DISCIPLINE),
                         {"Steel Works", "Electrical Works", "Pre Demolitioning", "Plumbing"})
        # Nothing is typed by position any more.
        self.assertNotIn(ProjectScope.ScopeType.STAGE, by_type)
        self.assertNotIn(ProjectScope.ScopeType.ZONE, by_type)

    def test_a_level_is_a_level_whether_or_not_a_part_is_coded(self):
        """Read positionally, "L.2" was the second surviving segment on rows
        that also carry a part and the first on rows that don't — a zone here,
        a stage there. The same level legitimately recurs under each part, so
        there is more than one node per name."""
        project = self._import()
        levels = ProjectScope.objects.filter(project=project, name__in=("L.2", "L.2A"))
        self.assertTrue(levels.exists())
        for level in levels:
            self.assertEqual(level.scope_type, ProjectScope.ScopeType.LEVEL)
            # Under its part where one is coded, at the root where none is —
            # never re-typed as something else either way.
            self.assertIn(level.parent.scope_type if level.parent else None,
                          {ProjectScope.ScopeType.PART, None})

    def test_the_report_reads_its_roles_off_this_shape(self):
        """No zone, no stage, no area type anywhere — the roles come from the
        tree: parts hold levels hold the work, so the level is the unit."""
        from apps.reports.services import _scope_roles

        project = self._import()
        self.assertEqual(
            _scope_roles(project, None),
            {"stage": ProjectScope.ScopeType.PART, "zone": ProjectScope.ScopeType.LEVEL,
             "area": None})

    def test_each_level_is_labelled_with_the_heading_that_names_it(self):
        """The codes are the team's own shorthand and the report goes to the
        client, so each level carries the file's own wording. The headings
        nest the other way round, so this can't be positional — matching by
        position labelled the "P1" part "Civil Works" (2026-09-08)."""
        project = self._import()
        labels = dict(ProjectScope.objects.filter(project=project).values_list("name", "label"))
        self.assertEqual(labels["P1"], "Part 1")
        self.assertEqual(labels["L.2"], "Level 2")
        self.assertEqual(labels["L.2A"], "Level 2A")
        self.assertEqual(labels["Civil"], "Civil Works")
        self.assertEqual(labels["MEP"], "MEP Works")
        self.assertEqual(labels["Steel Works"], "Steel Works")
        self.assertEqual(labels["Pre Demolitioning"], "Pre-Demolishing")

    def test_the_report_shows_those_names_not_the_codes(self):
        """"P1 - L.2A" means nothing to the client reading the report."""
        from apps.reports.services import _text

        project = self._import()
        part = ProjectScope.objects.filter(project=project, name="P1").first()
        self.assertEqual(_text(part), "Part 1")
        unlabelled = ProjectScope.objects.filter(project=project, label="").first()
        if unlabelled is not None:            # falls back, never blank
            self.assertEqual(_text(unlabelled), unlabelled.name)


class HeadingToSlotTests(SimpleTestCase):
    """Which WBS heading names which coded level. The two describe the same
    tree in different orders — Cairo Airport nests headings discipline >
    sub-discipline > level > part while its legend declares part, level,
    discipline, sub-discipline — so they can't be paired by position, and not
    by indentation depth either: that file puts parts and work packages at the
    same depth in different branches (2026-09-08)."""

    def _observed(self):
        # Every heading with the code values seen under it, as the parser
        # gathers them.
        return {
            ("Construction",): {"discipline": {"Civil", "MEP"}, "sub_discipline": {"Steel", "Block"},
                                "level": {"L.2", "L.2A"}, "part": {"P1", "P2"}},
            ("Construction", "Civil Works"): {"discipline": {"Civil"}, "sub_discipline": {"Steel", "Block"},
                                              "level": {"L.2", "L.2A"}, "part": {"P1", "P2"}},
            ("Construction", "Civil Works", "Steel Works"): {
                "discipline": {"Civil"}, "sub_discipline": {"Steel"},
                "level": {"L.2", "L.2A"}, "part": {"P1", "P2"}},
            ("Construction", "Civil Works", "Steel Works", "Level 2"): {
                "discipline": {"Civil"}, "sub_discipline": {"Steel"},
                "level": {"L.2"}, "part": {"P1", "P2"}},
            ("Construction", "Civil Works", "Steel Works", "Level 2", "Part 1"): {
                "discipline": {"Civil"}, "sub_discipline": {"Steel"},
                "level": {"L.2"}, "part": {"P1"}},
        }

    def test_a_heading_names_the_slot_it_settles(self):
        from .p6_id_schedule_import import _headings_by_slot

        self.assertEqual(_headings_by_slot(self._observed()), {
            ("discipline", "Civil"): "Civil Works",
            ("sub_discipline", "Steel"): "Steel Works",
            ("level", "L.2"): "Level 2",
            ("part", "P1"): "Part 1",
        })

    def test_a_heading_that_settles_two_slots_at_once_names_neither(self):
        """A heading with no code counterpart of its own ("Split high wall
        unit" under HVAC) happens to sit above one part AND one level. Naming
        it either would be a guess."""
        from .p6_id_schedule_import import _headings_by_slot

        observed = self._observed()
        observed[("Construction", "Civil Works", "Steel Works", "Sundries")] = {
            "discipline": {"Civil"}, "sub_discipline": {"Steel"},
            "level": {"L.2"}, "part": {"P1"}}
        named = _headings_by_slot(observed)
        self.assertNotIn("Sundries", named.values())

    def test_the_root_heading_names_nothing(self):
        """Everything varies under it, so it settles no slot at all."""
        from .p6_id_schedule_import import _headings_by_slot

        self.assertNotIn("Construction", _headings_by_slot(self._observed()).values())

    def test_no_headings_yields_no_names(self):
        from .p6_id_schedule_import import _headings_by_slot

        self.assertEqual(_headings_by_slot({}), {})
