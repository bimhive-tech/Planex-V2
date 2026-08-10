"""Import P6 schedules that carry a separate "Planex Code" column encoding
the WBS hierarchy, alongside the normal Activity ID/Name columns.

Verified against the team's first real export (Mansoura 6 - Building,
Aug 2026) — this replaces an earlier version of this module that was built
entirely from the 12-column legend sheet alone, before any real file
existed, and guessed wrong in several ways (see git history if curious).
Real shape, empirically confirmed against ~24k populated rows of one file:

  - The Planex Code lives in its OWN column ("Planex Code"), separate from
    "Activity ID" — it is NOT the Activity ID itself. Activity ID/Name stay
    the leaf activity's own identity (its code and description); Planex
    Code only drives the WBS tree structure.
  - Segments are dash-separated. The first segment is the project's own
    code (e.g. "MN(6)") — dropped, redundant with project.name, same as
    the old scheme's PN. The last segment is a per-row differentiator
    (e.g. "1", "2", ...) — dropped too, since the real Activity ID is a
    better, file-native code for the leaf activity than a synthetic one.
  - A middle segment is a PLACEHOLDER — this row doesn't branch on that
    legend level — when it's exactly "0", or exactly equals one of the
    legend's own bare tag words (CON, AR, SAR/SUB AR, PH, Z, P, U, LEV,
    DEC, SUB DEC) with no distinguishing suffix, e.g. "CON" alone vs
    "PH1"/"Z(A)". Every other middle segment is kept, in order, as a real
    tree level — its raw text (e.g. "PH1", "Z(A)", "Building 6", "Internal
    Finishes") is both the grouping key and the human-readable label; there
    is no need to know which of the legend's 12 named slots it originally
    filled.

This is deliberately content-based rather than a fixed 12-slot regex: the
legend sheet's own "0 vs omitted entirely" convention was inconsistent even
within ONE project's real file — Area/Sub-area/Part kept a literal "0"
placeholder in the string, while Level/Sub-discipline were dropped from it
entirely (10 dash-separated segments on every real row, not 12). A fixed-
position parser would have to special-case that exact combination and
would break the moment a different project's legend uses a different one
(the legend sheet is set up per-project, so it can vary). Matching by
content instead of position tolerates any combination without needing to
special-case each one.
"""
from .p6_schedule_import import _int, _locate_header, _num, _parse_date, _to_pct

# Bare tag words that mean "this legend level isn't used on this row" when
# they appear with no distinguishing suffix (contrast "CON" alone vs "PH1").
_PLACEHOLDER_WORDS = {"pn", "con", "ar", "sub ar", "sar", "ph", "z", "p", "u", "lev", "dec", "sub dec", "sdec", "nu"}

_SAMPLE_SIZE = 30  # rows sampled to decide whether a sheet uses this scheme
_MATCH_RATIO = 0.6  # majority, not unanimous — a few malformed/legacy rows shouldn't disqualify a whole sheet
_MIN_SEGMENTS = 3  # project code + at least one real level + differentiator


def segment_path(code: str) -> list:
    """The real (non-placeholder) middle segments of one Planex Code, in
    order — dropping the leading project code and trailing differentiator.
    [] if `code` doesn't look like a dash-segmented code at all (too few
    parts, or every middle segment is a placeholder)."""
    if not isinstance(code, str):
        return []
    parts = [p.strip() for p in code.strip().split("-")]
    if len(parts) < _MIN_SEGMENTS:
        return []
    middle = parts[1:-1]
    return [p for p in middle if p and p != "0" and p.lower() not in _PLACEHOLDER_WORDS]


def _looks_like_planex_code(rows, code_col) -> bool:
    seen = hits = 0
    for row in rows:
        v = row[code_col] if code_col < len(row) else None
        if not isinstance(v, str) or not v.strip():
            continue
        seen += 1
        if len(v.strip().split("-")) >= _MIN_SEGMENTS:
            hits += 1
        if seen >= _SAMPLE_SIZE:
            break
    return seen > 0 and hits / seen >= _MATCH_RATIO


def _new_group(name: str) -> dict:
    return {"name": name[:180] or "Uncategorized", "children": [], "activities": [],
            "start": None, "finish": None, "pct": None, "schedule_pct": None}


def _rollup_dates(node):
    """Synthesized group nodes carry no Start/Finish of their own (there's no
    WBS row to read them from) — roll up min/max from descendants so the
    scope still gets planned dates, matching what the old parser gave for
    free from the source WBS rows."""
    starts, finishes = [], []
    if node["start"]:
        starts.append(node["start"])
    if node["finish"]:
        finishes.append(node["finish"])
    for task in node["activities"]:
        if task["start"]:
            starts.append(task["start"])
        if task["finish"]:
            finishes.append(task["finish"])
    for child in node["children"]:
        _rollup_dates(child)
        if child["start"]:
            starts.append(child["start"])
        if child["finish"]:
            finishes.append(child["finish"])
    node["start"] = min(starts) if starts else None
    node["finish"] = max(finishes) if finishes else None


def _milestone_group(rows, id_c, name_c, start_c, finish_c, pct_c):
    """Collect leaf activities that live under a WBS branch matching the
    milestone keywords (p6_schedule_import._is_milestone_group), located by
    the file's own leading-space indentation on the Activity ID column —
    NOT by Planex Code, since these rows carry none at all. A real P6
    export keeps its key dates (project start/finish, handover milestones)
    as zero-work activities under one WBS heading; that heading isn't part
    of the coded discipline work, so the code-driven walk in
    parse_id_schedule_sheets never sees it and would otherwise silently
    drop every one of these rows.

    Returns a single synthetic group (named so it still matches the
    milestone keywords) for the caller to append to `roots` — build_from_
    p6_schedule's existing _extract_milestones step then picks it up and
    routes it to the Milestones panel exactly like the old indentation
    parser's own milestone branch, with no other special-casing needed."""
    from .p6_schedule_import import _is_milestone_group, _leading_spaces

    group = None
    stack = []  # (depth, is_milestone_branch)
    in_milestones = False
    for row in rows:
        act_id = row[id_c] if id_c < len(row) else None
        name = row[name_c] if name_c < len(row) else None
        if not isinstance(act_id, str) or not act_id.strip():
            continue
        a_str = act_id
        if isinstance(name, str) and name.strip():
            if in_milestones:
                start = _parse_date(row[start_c]) if start_c < len(row) else None
                finish = _parse_date(row[finish_c]) if finish_c < len(row) else None
                pct = row[pct_c] if pct_c is not None and pct_c < len(row) else None
                if group is None:
                    group = _new_group("Key Milestones")
                group["activities"].append({
                    "code": a_str.strip()[:60], "name": name.strip()[:200],
                    "pct": _to_pct(pct), "start": start, "finish": finish,
                    "budget": None, "earned_value": None, "float": None,
                    "duration": None, "remaining": None,
                })
            continue
        depth = _leading_spaces(a_str)
        while stack and stack[-1][0] >= depth:
            stack.pop()
        is_ms = _is_milestone_group(a_str.strip()) or (stack[-1][1] if stack else False)
        stack.append((depth, is_ms))
        in_milestones = is_ms
    return group


def parse_id_schedule_sheets(wb):
    """Return [{name, children, activities, start, finish}] built from a
    sheet's "Planex Code" column, or None if no sheet has one (or none of
    its values look like dash-segmented codes).

    Every row with a real (non-empty) Planex Code is a leaf: there are no
    separate WBS rows to detect, so unlike parse_p6_schedule_sheets this
    samples the Planex Code column's own values to decide whether a sheet
    uses this scheme at all."""
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        located = _locate_header(rows)
        if not located:
            continue
        header_idx, cols = located
        code_c = cols.get("planex code")
        if code_c is None:
            continue  # this sheet has no Planex Code column — not our scheme
        id_c, name_c = cols["activity id"], cols["activity name"]
        data_rows = rows[header_idx + 1:]
        if not _looks_like_planex_code(data_rows, code_c):
            continue

        start_c, finish_c = cols["start"], cols["finish"]
        pct_c = cols.get("activity % complete")
        dur_c = cols.get("original duration")
        rem_c = cols.get("remaining duration")
        float_c = cols.get("total float")
        # P6 export column naming for the cost figure has been seen as both
        # "Budgeted Material Cost" (the original reference template) and
        # "Budgeted Total Cost" (this file) — accept either.
        cost_c = cols.get("budgeted material cost")
        if cost_c is None:
            cost_c = cols.get("budgeted total cost")
        ev_c = cols.get("earned value cost")

        by_path: dict[tuple, dict] = {}
        roots: list[dict] = []

        def node_for(path: tuple) -> dict:
            """Get-or-create the group node at `path`, creating any missing
            ancestors along the way so an out-of-order file still nests
            correctly."""
            if path in by_path:
                return by_path[path]
            parent_children = roots
            built = ()
            for seg in path:
                built = built + (seg,)
                if built not in by_path:
                    by_path[built] = _new_group(seg)
                    parent_children.append(by_path[built])
                parent_children = by_path[built]["children"]
            return by_path[path]

        matched_any = False
        for row in data_rows:
            raw_code = row[code_c] if code_c < len(row) else None
            act_id = row[id_c] if id_c < len(row) else None
            name = row[name_c] if name_c < len(row) else None
            if not isinstance(raw_code, str) or not raw_code.strip():
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            path = tuple(segment_path(raw_code))
            if not path:
                continue
            matched_any = True

            start = _parse_date(row[start_c]) if start_c < len(row) else None
            finish = _parse_date(row[finish_c]) if finish_c < len(row) else None
            pct = row[pct_c] if pct_c is not None and pct_c < len(row) else None
            code = act_id.strip()[:60] if isinstance(act_id, str) and act_id.strip() else raw_code.strip()[:60]
            task = {
                "code": code, "name": name.strip()[:200],
                "pct": _to_pct(pct), "start": start, "finish": finish,
                "budget": _num(row, cost_c), "earned_value": _num(row, ev_c),
                "float": _int(row, float_c), "duration": _int(row, dur_c),
                "remaining": _int(row, rem_c),
            }
            node_for(path)["activities"].append(task)

        if not matched_any:
            continue

        # The Key Milestones WBS branch carries no Planex Code at all (see
        # _milestone_group's docstring) — the code-driven walk above never
        # sees it, so it's collected separately by indentation and appended
        # here; build_from_p6_schedule's existing milestone extraction then
        # routes it to the Milestones panel like it always has.
        milestones = _milestone_group(data_rows, id_c, name_c, start_c, finish_c, pct_c)
        if milestones:
            roots.append(milestones)

        for root in roots:
            _rollup_dates(root)
        return roots or None
    return None
