"""Tests for the segmented-ID P6 parser (p6_id_schedule_import.py).

No real export using this scheme exists yet — these are built against the
12-column legend alone (PN/CON/AR/SUB AR/PH/Z/P/U/LEV/DEC/SUB DEC/NU), so they
document the assumed ID format as much as they verify behaviour. Revisit once
the team's real file arrives.
"""
import datetime
import io

import openpyxl
from django.test import TestCase

from apps.accounts.models import Company

from .imports import import_workbook
from .models import Activity, Project, ProjectScope
from .p6_id_schedule_import import parse_segmented_id


class ParseSegmentedIdTests(TestCase):
    def test_parses_all_twelve_segments(self):
        segs = parse_segmented_id("PN01-CON02-AR03-SAR00-PH04-Z00-P00-U00-LEV00-DEC02-SDEC00-NU007")
        self.assertEqual(segs, {
            "pn": 1, "con": 2, "ar": 3, "sar": 0, "ph": 4, "z": 0, "p": 0,
            "u": 0, "lev": 0, "dec": 2, "sdec": 0, "nu": 7,
        })

    def test_rejects_malformed_id(self):
        self.assertIsNone(parse_segmented_id("Not-A-Segmented-Id"))
        self.assertIsNone(parse_segmented_id("PN01-CON02-AR03"))  # too few segments


class SegmentedIdImportTests(TestCase):
    """Same header shape as the reference P6 schedule export, but with
    segmented Activity IDs and no separate WBS rows — every row is a leaf."""

    HEADER = ["Activity ID", "Activity Name", "Original Duration", "Start", "Finish",
              "Activity % Complete", "Budgeted Material Cost", "Earned Value Cost"]

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

    def test_builds_tree_from_shared_id_prefixes(self):
        d = datetime.date
        rows = [
            # Two activities sharing CON01-AR01-PH01 -> one Stage/Zone/Phase branch.
            ["PN01-CON01-AR01-SAR00-PH01-Z00-P00-U00-LEV00-DEC00-SDEC00-NU001", "Excavate",
             10, d(2026, 1, 1), d(2026, 1, 10), 0.5, 1000, 500],
            ["PN01-CON01-AR01-SAR00-PH01-Z00-P00-U00-LEV00-DEC00-SDEC00-NU002", "Backfill",
             5, d(2026, 1, 11), d(2026, 1, 15), 0, 500, 0],
            # A second Area under the same Stage.
            ["PN01-CON01-AR02-SAR00-PH02-Z00-P00-U00-LEV00-DEC00-SDEC00-NU003", "Wiring",
             8, d(2026, 2, 1), d(2026, 2, 8), 1, 2000, 2000],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")

        result = import_workbook(project, self._workbook(rows), source="segmented.xlsx")
        self.assertEqual(result["source_kind"], "p6_schedule")
        self.assertEqual(result["activities"], 3)

        stage = ProjectScope.objects.get(project=project, name="CON 01")
        self.assertEqual(stage.scope_type, ProjectScope.ScopeType.STAGE)
        self.assertEqual(stage.parent, None)

        areas = list(ProjectScope.objects.filter(project=project, parent=stage).order_by("name"))
        self.assertEqual([a.name for a in areas], ["AR 01", "AR 02"])
        self.assertEqual(areas[0].scope_type, ProjectScope.ScopeType.ZONE)

        # PH01 holds activities directly -> becomes a Phase, whatever its depth.
        phase = ProjectScope.objects.get(project=project, name="PH 01")
        self.assertEqual(phase.scope_type, ProjectScope.ScopeType.PHASE)
        self.assertEqual(phase.parent, areas[0])

        excavate = Activity.objects.get(project=project, code="NU001")
        self.assertEqual(excavate.name, "Excavate")
        self.assertEqual(float(excavate.progress_percent), 50.0)

        # Group nodes carry no Start/Finish of their own — rolled up from activities.
        self.assertEqual(stage.planned_start, d(2026, 1, 1))
        self.assertEqual(stage.planned_finish, d(2026, 2, 8))

    def test_uneven_depth_still_resolves_holder_to_phase(self):
        """A branch that goes all the way to Level still becomes Phase at
        whatever depth actually holds the activity — same rule the leading-
        space parser already relies on for uneven WBS branches."""
        d = datetime.date
        rows = [
            ["PN01-CON01-AR01-SAR02-PH01-Z03-P01-U01-LEV02-DEC00-SDEC00-NU001", "Deep leaf",
             10, d(2026, 1, 1), d(2026, 1, 10), 0, 100, 0],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        import_workbook(project, self._workbook(rows), source="segmented.xlsx")

        leaf_scope = Activity.objects.get(project=project, code="NU001").scope
        self.assertEqual(leaf_scope.scope_type, ProjectScope.ScopeType.PHASE)
        self.assertEqual(leaf_scope.name, "LEV 02")

    def test_all_placeholder_tree_segments_fall_back_to_uncategorized(self):
        d = datetime.date
        rows = [
            ["PN01-CON00-AR00-SAR00-PH00-Z00-P00-U00-LEV00-DEC00-SDEC00-NU001", "Orphan task",
             1, d(2026, 1, 1), d(2026, 1, 2), 0, 0, 0],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        import_workbook(project, self._workbook(rows), source="segmented.xlsx")

        self.assertTrue(ProjectScope.objects.filter(project=project, name="Uncategorized").exists())

    def test_leading_space_export_still_takes_the_old_path(self):
        """A file using the old indentation scheme has no segmented IDs at all,
        so detection must fall through to parse_p6_schedule_sheets untouched."""
        d = datetime.date
        rows = [
            ["  Construction Phase", None, 0, d(2026, 1, 1), d(2026, 2, 1), None, 0, 0],
            ["CN.01", "Foundation", 10, d(2026, 1, 1), d(2026, 1, 10), 0.5, 1000, 500],
        ]
        company = Company.objects.create(name="Acme")
        project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        result = import_workbook(project, self._workbook(rows), source="legacy.xlsx")
        self.assertEqual(result["source_kind"], "p6_schedule")
        self.assertTrue(ProjectScope.objects.filter(project=project, name="Construction Phase").exists())
