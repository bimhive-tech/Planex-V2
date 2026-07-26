"""Import the real Primavera P6 schedule export.

Unlike the legacy 'FOR (P6)' sheet (p6_import.py), this is a genuine P6-to-Excel
export: a single flat sheet with real columns (Activity ID, Activity Name,
Original Duration, Start, Finish, Activity % Complete, ...) where the WBS
hierarchy is encoded as LEADING SPACES in the Activity ID column's text — P6
doesn't set Excel outline levels for this export, so indentation is the only
signal. A group/WBS row has a name in Activity ID and nothing in Activity Name;
a leaf activity row has both, with 0 leading spaces regardless of its actual
depth (it always belongs to whichever WBS group most recently appeared above
it). This is the standard schedule-import template going forward — tried before
the zone-tracker matrix parser in imports.import_workbook.
"""
import datetime
import re
from collections import defaultdict

import openpyxl

from .models import Activity, ProjectScope

# Only the columns we actually read are required, so minor template variations
# (extra/missing Primavera columns) still match.
_REQUIRED_HEADERS = ("activity id", "activity name", "start", "finish", "activity % complete")
_HEADER_SCAN_ROWS = 3
_DATE_RX = re.compile(r"(\d{1,2})-([A-Za-z]{3})-(\d{2})")


def _header_cols(row):
    return {str(c or "").strip().lower(): i for i, c in enumerate(row)}


def _locate_header(rows):
    for idx in range(min(_HEADER_SCAN_ROWS, len(rows))):
        cols = _header_cols(rows[idx])
        if all(h in cols for h in _REQUIRED_HEADERS):
            return idx, cols
    return None


def _parse_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        m = _DATE_RX.search(v)  # strips trailing " A" (actual) / "*" (constrained)
        if m:
            try:
                return datetime.datetime.strptime("-".join(m.groups()), "%d-%b-%y").date()
            except ValueError:
                return None
    return None


def _to_pct(v):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return 0.0
    pct = v * 100 if v <= 1.0001 else v
    return max(0.0, min(100.0, round(pct, 2)))


def _leading_spaces(s):
    return len(s) - len(s.lstrip(" "))


def parse_p6_schedule_tree(file_obj):
    """Return [{name, children, activities, start, finish}] from the first sheet
    matching this template, or None if no sheet does."""
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    try:
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            located = _locate_header(rows)
            if not located:
                continue
            header_idx, cols = located
            id_c, name_c = cols["activity id"], cols["activity name"]
            start_c, finish_c = cols["start"], cols["finish"]
            dur_c = cols.get("original duration")
            pct_c = cols.get("activity % complete")

            roots, stack = [], []  # stack of (depth, node)
            for row in rows[header_idx + 1:]:
                a = row[id_c] if id_c < len(row) else None
                if a is None or (isinstance(a, str) and not a.strip()):
                    continue
                a_str = str(a)
                b = row[name_c] if name_c < len(row) else None
                start = _parse_date(row[start_c]) if start_c < len(row) else None
                finish = _parse_date(row[finish_c]) if finish_c < len(row) else None

                if isinstance(b, str) and b.strip():  # leaf activity
                    if not stack:
                        continue  # no parent WBS group to root it under
                    dur = row[dur_c] if dur_c is not None and dur_c < len(row) else None
                    pct = row[pct_c] if pct_c is not None and pct_c < len(row) else None
                    stack[-1][1]["activities"].append({
                        "code": a_str.strip()[:60], "name": b.strip()[:200],
                        "pct": _to_pct(pct), "start": start, "finish": finish,
                        "weight": float(dur) if isinstance(dur, (int, float)) and dur > 0 else 1.0,
                    })
                    continue

                depth = _leading_spaces(a_str)
                node = {"name": a_str.strip()[:180], "children": [], "activities": [],
                       "start": start, "finish": finish}
                while stack and stack[-1][0] >= depth:
                    stack.pop()
                (stack[-1][1]["children"] if stack else roots).append(node)
                stack.append((depth, node))
            return roots or None
    finally:
        wb.close()
    return None


def _entry_nodes(roots):
    """The project-title row parses as a single depth-0 WBS wrapper around the
    real top-level groups — unwrap it so we don't create a redundant scope
    that just repeats the project's own name."""
    if len(roots) == 1 and not roots[0]["activities"] and roots[0]["children"]:
        return roots[0]["children"]
    return roots


def build_from_p6_schedule(project, roots, *, replace=True, snapshot_date=None, source=""):
    """Create scopes + activities from a parsed P6 schedule tree. Top-level
    groups become Stages; below that, a node holding activities directly is a
    Phase, anything else (a pure grouping level) is an Area."""
    from django.utils import timezone

    from .imports import _guess_discipline, _save_snapshot, parse_date_from_name
    from .services import project_overall_progress

    Scope = ProjectScope
    company = project.company
    if replace:
        project.scopes.all().delete()

    entries = _entry_nodes(roots)
    scopes_by_depth = defaultdict(list)
    activities = []
    counts = defaultdict(int)
    row_counter = [0]

    def type_of(node, forced):
        if forced:
            return forced
        return Scope.ScopeType.PHASE if node["activities"] else Scope.ScopeType.AREA

    def walk(node, parent, depth, forced):
        stype = type_of(node, forced)
        counts[stype] += 1
        scope = Scope(company=company, project=project, parent=parent, scope_type=stype,
                      name=node["name"], sort_order=len(scopes_by_depth[depth]),
                      planned_start=node.get("start"), planned_finish=node.get("finish"),
                      discipline=_guess_discipline(node["name"]) if stype == Scope.ScopeType.PHASE else "")
        scopes_by_depth[depth].append(scope)
        for task in node["activities"]:
            row_counter[0] += 1
            activities.append(Activity(
                company=company, project=project, scope=scope,
                name=task["name"], code=task["code"], weight=task["weight"],
                progress_percent=task["pct"], phase_name=node["name"],
                planned_start=task["start"], planned_finish=task["finish"],
                row_index=row_counter[0], sort_order=row_counter[0],
                progress_type=Activity.ProgressType.PERCENTAGE,
            ))
        for child in node["children"]:
            walk(child, scope, depth + 1, None)

    for entry in entries:
        walk(entry, None, 0, Scope.ScopeType.STAGE)

    # Parents before children (UUID PKs are generated in Python, so we only need
    # insert order to satisfy the FK).
    for depth in sorted(scopes_by_depth):
        Scope.objects.bulk_create(scopes_by_depth[depth], batch_size=1000)
    Activity.objects.bulk_create(activities, batch_size=2000)

    snap_date = snapshot_date or parse_date_from_name(source) or timezone.now().date()
    _save_snapshot(project, date=snap_date, source=source)

    return {
        "stages": counts.get(Scope.ScopeType.STAGE, 0),
        "zones": 0,
        "subzones": counts.get(Scope.ScopeType.AREA, 0),
        "phases": counts.get(Scope.ScopeType.PHASE, 0),
        "activities": len(activities),
        "overall_progress": project_overall_progress(project),
        "snapshot_date": snap_date.isoformat(),
        "source_kind": "p6_schedule",
    }
