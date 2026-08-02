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
import itertools
import re
from collections import defaultdict
from decimal import Decimal

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


def _to_pct_optional(v):
    """Like _to_pct, but None (not 0.0) when there's no real value — needed to
    tell "this WBS row has no Performance % Complete" apart from "it's 0%"."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    return _to_pct(v)


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
    """Convenience wrapper: open `file_obj` read-only and parse it. Callers that
    already hold an open workbook should use parse_p6_schedule_sheets instead —
    opening a 20MB+ tracker costs ~26s, so the import path shares one open."""
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    try:
        return parse_p6_schedule_sheets(wb)
    finally:
        wb.close()


def parse_p6_schedule_sheets(wb):
    """Return [{name, children, activities, start, finish}] from the first sheet
    of `wb` matching this template, or None if no sheet does.

    This runs on EVERY import as a format probe, so a sheet that isn't ours must
    be cheap to reject: we pull only the few rows the header could be on and move
    to the next sheet if it doesn't match. Reading the whole sheet up front
    instead would materialise ~1.5M cells of a big zone tracker's 'FOR (P6)' tab
    just to throw them away."""
    for ws in wb.worksheets:
        stream = ws.iter_rows(values_only=True)
        head, located = [], None
        for row in stream:
            head.append(row)
            located = _locate_header(head)
            if located or len(head) >= _HEADER_SCAN_ROWS:
                break
        if not located:
            continue
        header_idx, cols = located
        # Rows after the header: what's left of the peeked rows, then the rest.
        rows = itertools.chain(head[header_idx + 1:], stream)
        id_c, name_c = cols["activity id"], cols["activity name"]
        start_c, finish_c = cols["start"], cols["finish"]
        pct_c = cols.get("activity % complete")
        dur_c = cols.get("original duration")
        rem_c = cols.get("remaining duration")
        float_c = cols.get("total float")
        cost_c = cols.get("budgeted material cost")
        ev_c = cols.get("earned value cost")
        perf_c = cols.get("performance % complete")  # actual (earned value / budget)
        sched_c = cols.get("schedule % complete")  # planned (time-based)

        roots, stack = [], []  # stack of (depth, node)
        for row in rows:
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
            perf = row[perf_c] if perf_c is not None and perf_c < len(row) else None
            sched = row[sched_c] if sched_c is not None and sched_c < len(row) else None
            node = {"name": a_str.strip()[:180], "children": [], "activities": [],
                    "start": start, "finish": finish,
                    "pct": _to_pct_optional(perf), "schedule_pct": _to_pct_optional(sched)}
            while stack and stack[-1][0] >= depth:
                stack.pop()
            (stack[-1][1]["children"] if stack else roots).append(node)
            stack.append((depth, node))
        return roots or None
    return None


def _entry_nodes(roots):
    """The project-title row parses as a single depth-0 WBS wrapper around the
    real top-level groups — unwrap it so we don't create a redundant scope
    that just repeats the project's own name."""
    if len(roots) == 1 and not roots[0]["activities"] and roots[0]["children"]:
        return roots[0]["children"]
    return roots


# A P6 schedule keeps its key dates as zero-work "milestone" activities, usually
# grouped under one WBS node. They are dates, not work: they carry no cost and no
# duration, so leaving them in the tree adds a branch that can never progress.
# They belong in the Milestones panel instead.
_MILESTONE_KEYWORDS = ("milestone", "النقاط الزمنية", "معالم")


def _is_milestone_group(name: str) -> bool:
    lowered = name.lower()
    return any(k in lowered for k in _MILESTONE_KEYWORDS)


def _subtree_activities(node):
    yield from node["activities"]
    for child in node["children"]:
        yield from _subtree_activities(child)


def _extract_milestones(roots) -> list:
    """Remove milestone groups from the tree, returning their activities so the
    caller can record them as Milestones."""
    found = []

    def walk(nodes):
        keep = []
        for node in nodes:
            if _is_milestone_group(node["name"]):
                found.extend(_subtree_activities(node))
                continue  # drop the whole group from the schedule
            node["children"] = walk(node["children"])
            keep.append(node)
        return keep

    roots[:] = walk(roots)
    return found


def _prune_empty(roots):
    """Drop branches that hold no activities anywhere. A P6 WBS carries planned-
    but-unpopulated headings (e.g. a 'Super Structure' with nothing under it);
    as scopes they are dead rows that can never show progress."""

    def keep(node):
        node["children"] = [c for c in node["children"] if keep(c)]
        return bool(node["activities"] or node["children"])

    roots[:] = [r for r in roots if keep(r)]


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


def _record_milestones(project, tasks):
    """Store milestone activities as Milestones. Upserted by title rather than
    replaced wholesale so re-importing an updated schedule refreshes the dates
    without discarding milestones somebody added by hand."""
    from .models import Milestone

    for order, task in enumerate(tasks):
        pct = task["pct"]
        status = (Milestone.Status.COMPLETED if pct >= 100
                  else Milestone.Status.IN_PROGRESS if pct > 0
                  else Milestone.Status.UPCOMING)
        Milestone.objects.update_or_create(
            project=project, title=task["name"][:180],
            defaults={"company": project.company, "sort_order": order, "status": status,
                      "date": task["finish"] or task["start"]},
        )
    return len(tasks)


def build_from_p6_schedule(project, roots, *, replace=True, snapshot_date=None, source="",
                          unwrap_single_root=True):
    """Create scopes + activities from a parsed P6 schedule tree.

    Scope type comes from a node's height above the activities, so the shape
    matches the hierarchy the rest of the app expects — Stage > Zone > Area >
    Phase > Activity — regardless of how deep a given WBS branch runs. The
    Phase level is the one that directly holds work, and Zone is what the
    Excel-style grid view pivots on.

    `unwrap_single_root`: the leading-space scheme's lone top row just repeats
    the project's own name (see _entry_nodes) and should be dropped. The
    segmented-ID scheme (p6_id_schedule_import) has no such wrapper — its
    "CON" segment is a real Stage level that can legitimately be the file's
    only root — so its caller passes False; unwrapping there would silently
    delete the whole Stage level whenever a file has just one Construction
    code, which is the common case."""
    from django.utils import timezone

    from .imports import _guess_discipline, _save_snapshot, parse_date_from_name
    from .services import project_overall_progress

    Scope = ProjectScope
    company = project.company
    if replace:
        project.scopes.all().delete()

    # The project-title row (before it's unwrapped below) carries the file's OWN
    # stated actual (Performance % Complete — earned value / budgeted cost, the
    # same thing our cost weighting approximates) and planned (Schedule %
    # Complete — time-based) progress. Prefer both over our own formulas: they're
    # what the source schedule itself reports.
    project_pct = roots[0].get("pct") if len(roots) == 1 and unwrap_single_root else None
    project_schedule_pct = roots[0].get("schedule_pct") if len(roots) == 1 and unwrap_single_root else None

    milestone_tasks = _extract_milestones(roots)
    _prune_empty(roots)
    entries = _entry_nodes(roots) if unwrap_single_root else roots
    weight_key = _weight_key(roots)

    scopes_by_depth = defaultdict(list)
    activities = []
    counts = defaultdict(int)
    row_counter = [0]

    def weight_of(task):
        """Nominal 1 when this activity has no value in the chosen column. It
        keeps an all-zero-cost branch rolling up on its own merits instead of
        dividing by a zero weight sum, while staying negligible against real
        cost weights."""
        value = task.get(weight_key) if weight_key else None
        return value if value and value > 0 else 1.0

    # Level comes from depth below the top of the WBS, which is how a planner
    # reads it: the project splits into Stages, a Stage into Zones, a Zone into
    # Areas. Measuring up from the activities instead sounds tidier but WBS
    # branches are wildly uneven — 'Construction Phase' runs four levels deep
    # where 'Technical Service' runs two — so the same "Civil Works" heading
    # lands on a different level in each branch.
    _BY_DEPTH = {0: Scope.ScopeType.STAGE, 1: Scope.ScopeType.ZONE, 2: Scope.ScopeType.AREA}

    def type_of(node, depth):
        # Holding work always wins: that node is the work package, whatever depth
        # it sits at, and the grid looks for activities under a Phase.
        if node["activities"]:
            return Scope.ScopeType.PHASE
        return _BY_DEPTH.get(depth, Scope.ScopeType.AREA)

    def walk(node, parent, depth, grid):
        """`grid` carries the enclosing zone's column context: (index, name, rows)
        where rows maps a task to its grid row, so the same task under different
        columns lands on one row."""
        stype = type_of(node, depth)
        counts[stype] += 1
        scope = Scope(company=company, project=project, parent=parent, scope_type=stype,
                      name=node["name"], sort_order=len(scopes_by_depth[depth]),
                      planned_start=node.get("start"), planned_finish=node.get("finish"),
                      discipline=_guess_discipline(node["name"]) if stype == Scope.ScopeType.PHASE else "")
        scopes_by_depth[depth].append(scope)

        for task in node["activities"]:
            row_counter[0] += 1
            col_index, col_name, rows = grid if grid else (0, "", None)
            if rows is None:
                row_index = row_counter[0]
            else:
                # Rows are keyed per (phase, task) so a task repeated across the
                # zone's columns shares one row instead of stacking up.
                row_index = rows.setdefault((node["name"], task["name"]), len(rows) + 1)
            activities.append(Activity(
                company=company, project=project, scope=scope,
                name=task["name"], code=task["code"], weight=weight_of(task),
                progress_percent=task["pct"], phase_name=node["name"],
                planned_start=task["start"], planned_finish=task["finish"],
                budgeted_cost=task["budget"], earned_value_cost=task["earned_value"],
                total_float=task["float"], original_duration=task["duration"],
                remaining_duration=task["remaining"],
                row_index=row_index, sort_order=row_counter[0],
                subzone_index=col_index, subzone_code=col_name,
                progress_type=Activity.ProgressType.PERCENTAGE,
            ))

        # A Zone opens a fresh grid; each of its children is one column.
        if stype == Scope.ScopeType.ZONE:
            rows = {}
            for index, child in enumerate(node["children"]):
                walk(child, scope, depth + 1, (index, child["name"][:80], rows))
        else:
            for child in node["children"]:
                walk(child, scope, depth + 1, grid)

    for entry in entries:
        walk(entry, None, 0, None)

    # Parents before children (UUID PKs are generated in Python, so we only need
    # insert order to satisfy the FK).
    for depth in sorted(scopes_by_depth):
        Scope.objects.bulk_create(scopes_by_depth[depth], batch_size=1000)
    Activity.objects.bulk_create(activities, batch_size=2000)

    milestones = _record_milestones(project, milestone_tasks)

    project.imported_progress_percent = Decimal(str(project_pct)) if project_pct is not None else None
    project.imported_planned_progress_percent = (
        Decimal(str(project_schedule_pct)) if project_schedule_pct is not None else None
    )
    project.save(update_fields=[
        "imported_progress_percent", "imported_planned_progress_percent", "updated_at",
    ])

    # _save_snapshot below calls project_overall_progress(project) with no as-of
    # override, so it picks up imported_progress_percent (just set above) as the
    # "current" figure — the report's progress history now agrees with the
    # source schedule's own number instead of our approximation of it.
    snap_date = snapshot_date or parse_date_from_name(source) or timezone.now().date()
    _save_snapshot(project, date=snap_date, source=source)

    return {
        "stages": counts.get(Scope.ScopeType.STAGE, 0),
        "zones": counts.get(Scope.ScopeType.ZONE, 0),
        "subzones": counts.get(Scope.ScopeType.AREA, 0),
        "phases": counts.get(Scope.ScopeType.PHASE, 0),
        "milestones": milestones,
        "activities": len(activities),
        "overall_progress": project_overall_progress(project),
        "overall_progress_source": "imported" if project_pct is not None else "computed",
        "planned_progress": float(project_schedule_pct) if project_schedule_pct is not None else None,
        "snapshot_date": snap_date.isoformat(),
        "source_kind": "p6_schedule",
        "weighted_by": weight_key or "equal",  # surfaced so the UI can say how % was derived
    }
