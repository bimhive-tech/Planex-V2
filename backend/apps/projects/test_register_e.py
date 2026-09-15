"""Register section E: the schedule page.

  E1  one import dialog: a dashboard import is linked to its data date
  E2  the schedule tree follows the Planex Code level by level — Area ›
      Sub-area › Phase › Zone › Part › Unit › Level › Discipline ›
      Sub-discipline — with every empty level its own "No …" row
"""
import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.constants import COMPANY_ADMIN_PERMISSIONS, SeededRole
from apps.accounts.models import Company, Membership, Role, User

from . import test_p6_id_schedule_import as p6_tests
from .models import Activity, DashboardImport, Project


class PlanexCodeChainTests(TestCase):
    """E2, on the Cairo file's own shape (p6_tests.LegendReadImportTests' workbook)."""

    # Borrowed rather than inherited, so that class's own tests don't run twice.
    HEADER = p6_tests.LegendReadImportTests.HEADER
    LEGEND = p6_tests.LegendReadImportTests.LEGEND
    _workbook = p6_tests.LegendReadImportTests._workbook
    _import = p6_tests.LegendReadImportTests._import

    def _chain(self, name):
        scope = Activity.objects.get(project=self.project, name=name).scope
        chain = []
        while scope is not None:
            chain.append(scope)
            scope = scope.parent
        return list(reversed(chain))

    def setUp(self):
        self.project = self._import()

    def test_every_level_of_the_code_is_its_own_row_in_the_legends_order(self):
        chain = self._chain("Conduits")  # CA-CON-0-0-0-0-P2-0-L.2A-MEP-Electrical Works-358
        self.assertEqual([s.scope_type for s in chain], [
            "area", "sub_area", "stage", "zone", "part", "unit", "level", "discipline", "sub_discipline"])
        self.assertEqual([s.display_name for s in chain[:4]], ["No area", "No sub-area", "No phase", "No zone"])
        self.assertEqual(chain[4].name, "P2")
        self.assertEqual(chain[5].display_name, "No unit")
        self.assertEqual((chain[6].name, chain[7].name, chain[8].name), ("L.2A", "MEP", "Electrical Works"))

    def test_the_project_name_and_construction_slots_are_not_levels(self):
        roots = self.project.scopes.filter(parent__isnull=True)
        self.assertEqual([(s.scope_type, s.display_name) for s in roots], [("area", "No area")])

    def test_a_row_with_no_part_still_passes_through_every_level(self):
        chain = self._chain("Metal fence")  # CA-CON-0-0-0-0-0-0-0-Civil-Pre Demolitioning-1
        self.assertEqual(len(chain), 9)
        self.assertEqual([s.display_name for s in chain[4:7]], ["No part", "No unit", "No level"])


class ReportReadsThroughEmptyLevelsTests(TestCase):
    """E2: the report treats an empty level as not there — no "No level" zone,
    no "0" trade, and names told apart by the Part, not by the empty unit."""

    HEADER = p6_tests.LegendReadImportTests.HEADER
    LEGEND = p6_tests.LegendReadImportTests.LEGEND
    _workbook = p6_tests.LegendReadImportTests._workbook
    _import = p6_tests.LegendReadImportTests._import

    def setUp(self):
        from apps.projects.services import latest_schedule_import

        self.project = self._import()
        self.batch = latest_schedule_import(self.project)

    def test_zones_skip_empty_levels_and_are_named_by_their_part(self):
        from apps.reports.services import _hierarchy_rows, _zone_rows

        zones = [z["name"] for z in _zone_rows(self.project, schedule_import=self.batch)]
        self.assertTrue(zones)
        self.assertFalse([n for n in zones if n.startswith(("No ", "0"))], zones)
        self.assertIn("Part 1 - Level 2", zones)
        hierarchy = _hierarchy_rows(self.project, schedule_import=self.batch)
        self.assertEqual([z["name"] for z in hierarchy], zones)
        children = [c["name"] for z in hierarchy for c in z["children"]]
        self.assertFalse([n for n in children if n.startswith(("No ", "0"))], children)
        stages = {z["stage"] for z in hierarchy}
        self.assertTrue(stages <= {"", "Part 1", "Part 2", "P1", "P2"}, stages)

    def test_trades_and_work_packages_are_never_an_empty_slot(self):
        from apps.reports.services import _discipline_rows, _work_rows

        trades = [r["name"] for r in _work_rows(self.project, schedule_import=self.batch)]
        self.assertTrue(trades)
        self.assertNotIn("0", trades)
        columns, rows = _discipline_rows(self.project, schedule_import=self.batch)
        self.assertTrue(columns)
        self.assertFalse([c for c in columns if c.startswith(("No ", "0"))], columns)
        self.assertFalse([r["name"] for r in rows if r["name"].startswith(("No ", "0"))])


class DashboardImportDateTests(TestCase):
    """E1: the import dialog links a dashboard upload to its data date."""

    def setUp(self):
        company = Company.objects.create(name="Acme")
        role = Role.objects.create(company=company, name=SeededRole.COMPANY_ADMIN,
                                   permissions=COMPANY_ADMIN_PERMISSIONS)
        self.user = User.objects.create_user(email="admin@acme.com", password="Str0ngPassw0rd!", company=company)
        Membership.objects.create(company=company, user=self.user, role=role)
        self.project = Project.objects.create(company=company, name="Tower", project_type="commercial")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _upload(self, name, **data):
        from apps.projects import finance_views

        result = {"imported": {"cashflow": {"months": 1}}, "skipped": {}}
        original = finance_views.import_dashboard
        finance_views.import_dashboard = lambda project, upload: result
        try:
            file = SimpleUploadedFile(name, b"PK", content_type="application/octet-stream")
            return self.client.post(f"/api/projects/{self.project.id}/dashboard/import/",
                                    {"file": file, **data}, format="multipart")
        finally:
            finance_views.import_dashboard = original

    def test_the_chosen_date_is_recorded_and_listed(self):
        res = self._upload("dashboard.xlsx", date="2026-08-02")
        self.assertEqual(res.status_code, 200, res.content)
        record = DashboardImport.objects.get(project=self.project)
        self.assertEqual(record.data_date, datetime.date(2026, 8, 2))
        listed = self.client.get(f"/api/projects/{self.project.id}/dashboard/imports/")
        self.assertEqual(listed.data[0]["data_date"], "2026-08-02")

    def test_without_a_date_the_file_name_supplies_one(self):
        self._upload("Dashboard 2026-07-31.xlsx")
        self.assertEqual(DashboardImport.objects.get(project=self.project).data_date, datetime.date(2026, 7, 31))

    def test_a_malformed_date_is_refused(self):
        res = self._upload("dashboard.xlsx", date="31/07/2026")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(DashboardImport.objects.exists())
