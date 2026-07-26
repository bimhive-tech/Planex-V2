"""Import the real Primavera P6 schedule export.

Unlike the legacy 'FOR (P6)' sheet (p6_import.py), this is a genuine P6-to-Excel
export: a single flat sheet whose columns are Activity ID, Activity Name,
Original/Actual/Remaining Duration, Start, Finish, Total Float, Activity /
Performance / Schedule % Complete, Budgeted Material Cost, Earned Value Cost and
Schedule Variance Index.

Shape of the sheet:
  • The WBS hierarchy is encoded as LEADING SPACES in the Activity ID column's
    text (2 per level) — P6 doesn't set Excel outline levels here, so
    indentation is the only signal.
  • A WBS/group row has its name in Activity ID and NOTHING in Activity Name;
    a leaf activity row has both, always at 0 indentation, and belongs to
    whichever WBS group most recently appeared above it.
  • The single depth-0 row is the project title, unwrapped so we don't create a
    scope that merely repeats the project's name.
  • Dates are datetimes except where P6 annotates them: "21-Aug-25 A" (actual)
    and "19-Nov-27*" (constrained) arrive as strings and are parsed too.
  • % complete columns are 0–1 fractions. Only "Activity % Complete" is set on
    leaves; the WBS rows' Performance/Schedule % are roll-ups we recompute.

Weighting is the subtle part — see _weight_key. This is the standard
schedule-import template going forward, tried before the zone-tracker matrix
parser in imports.import_workbook.
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


def _num(row, col):
    """A cell's numeric value, or None. None (not 0) so "column absent" and
    "genuinely zero" stay distinguishable — the weighting decision depends on it."""
    if col is None or col >= len(row):
        return None
    v = row[col]
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(row, col):
    v = _num(row, col)
    return int(v) if v is not None else None


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
            pct_c = cols.get("activity % complete")
            dur_c = cols.get("original duration")
            rem_c = cols.get("remaining duration")
            float_c = cols.get("total float")
            cost_c = cols.get("budgeted material cost")
            ev_c = cols.get("earned value cost")

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
                    pct = row[pct_c] if pct_c is not None and pct_c < len(row) else None
                    stack[-1][1]["activities"].append({
                        "code": a_str.strip()[:60], "name": b.strip()[:200],
                        "pct": _to_pct(pct), "start": start, "finish": finish,
                        "budget": _num(row, cost_c), "earned_value": _num(row, ev_c),
                        "float": _int(row, float_c), "duration": _int(row, dur_c),
                        "remaining": _int(row, rem_c),
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


def _weight_key(roots) -> str:
    """Which column drives roll-up weight, decided once for the whole file.

    P6 computes a WBS's % complete as (earned value / budgeted cost), and earned
    value IS pct x budgeted cost — so weighting by budgeted cost reproduces P6's
    own number exactly. Verified against the reference export: cost weighting
    gives 3.15%, matching its Performance % Complete, where duration weighting
    gave 4.04%. A schedule exported without costs falls back to duration, and
    one with neither to equal weight.

    Decided per-file rather than per-activity so the scheme stays predictable:
    mixing cost and duration weights across rows would compare unlike units."""
    totals = {"budget": 0.0, "duration": 0.0}

    def walk(node):
        for task in node["activities"]:
            totals["budget"] += task["budget"] or 0
            totals["duration"] += task["duration"] or 0
        for child in node["children"]:
            walk(child)

    for root in roots:
        walk(root)
    if totals["budget"] > 0:
        return "budget"
    return "duration" if totals["duration"] > 0 else ""


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
    weight_key = _weight_key(roots)
    scopes_by_depth = defaultdict(list)
    activities = []
    counts = defaultdict(int)
    row_counter = [0]

    def weight_of(task):
        """Nominal 1 when this activity has no value in the chosen column. It
        keeps an all-zero-cost branch (e.g. a milestones group) rolling up on
        its own merits instead of dividing by a zero weight sum, while staying
        negligible against real cost weights."""
        value = task.get(weight_key) if weight_key else None
        return value if value and value > 0 else 1.0

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
                name=task["name"], code=task["code"], weight=weight_of(task),
                progress_percent=task["pct"], phase_name=node["name"],
                planned_start=task["start"], planned_finish=task["finish"],
                budgeted_cost=task["budget"], earned_value_cost=task["earned_value"],
                total_float=task["float"], original_duration=task["duration"],
                remaining_duration=task["remaining"],
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
        "weighted_by": weight_key or "equal",  # surfaced so the UI can say how % was derived
    }
