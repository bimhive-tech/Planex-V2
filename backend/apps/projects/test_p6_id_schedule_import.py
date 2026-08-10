"""Tests for the Planex Code P6 parser (p6_id_schedule_import.py).

Built against the team's first real export (Mansoura 6 - Building, Aug
2026) — see that module's docstring for the empirically-confirmed shape.
"""
import datetime
import io

import openpyxl
from django.test import TestCase

from apps.accounts.models import Company

from .imports import import_workbook
from .models import Activity, Project, ProjectScope
from .p6_id_schedule_import import segment_path


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
        end_ms = Milestone.objects.get(project=project, title="Project end")
        self.assertEqual(end_ms.status, Milestone.Status.UPCOMING)  # pct=0

        # The milestone branch must not also appear as a schedule scope.
        self.assertFalse(ProjectScope.objects.filter(project=project, name="Key Milestones").exists())

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
