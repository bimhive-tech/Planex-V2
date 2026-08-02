"""Import P6 schedules that carry the new SEGMENTED Activity ID scheme.

The old export (p6_schedule_import.py) encodes the WBS hierarchy as leading
spaces on WBS-only rows, with leaf activities appearing on separate rows below
their WBS group. The user's team is replacing that with an explicit,
position-coded Activity ID: every row is a leaf activity, and its ID spells
out the full WBS path as fixed, typed segments — no indentation or separate
group rows needed.

Legend (12 segments, "CONSTRUCTION PHASE", left to right):
    PN  Project Name        AR  Area          PH  Phase        LEV Level
    CON Construction        SUB AR  Sub Area  Z   Zone         DEC Discipline
                                              P   Part          SUB DEC Sub-discipline
                                              U   Unit          NU  Activity Number

*** ASSUMPTIONS — nothing below is verified against a real file yet (the team
    has not sent one). Every choice here is called out so it's a one-line fix
    once the first real export arrives: ***

  1. Segments are dash-separated, always all 12, in the legend's exact order,
       e.g. "PN01-CON02-AR03-SAR00-PH04-Z00-P00-U00-LEV00-DEC02-SDEC00-NU007"
     — matches the user's own call to use placeholders even when a segment is
     empty, rather than omitting it (see typed placeholder discussion).
  2. "SUB AR" -> tag "SAR", "SUB DEC" -> tag "SDEC" (the legend shows the
     words with a space; an ID can't contain one, so this is a guess at the
     compact tag actually embedded in the ID).
  3. A segment is a PLACEHOLDER (not applicable at this branch) when its
     numeric part is all zeros, e.g. "SAR00", "Z00" — real values are >0.
  4. DEC / SUB DEC are numeric codes with no legend for what each number
     means yet, so they are NOT mapped onto ProjectScope.Discipline (that
     enum is fixed text like "electrical" — guessing a mapping could silently
     mislabel every phase). They're carried through as a raw note on the
     scope name only; _guess_discipline() keeps doing the keyword-on-name
     fallback until a real code table shows up.
  5. NU is the activity's own differentiator, not a tree level — it plus the
     Activity Name becomes the leaf Activity, same as "code" in the old parser.

Everything below CON/AR/SUB AR/PH/Z/P/U/LEV becomes a nested scope, one level
per non-placeholder segment present on a given row — branches are naturally
uneven (some rows use Part/Unit/Level, others stop at Phase), which
build_from_p6_schedule already tolerates: only the node that actually holds
activities becomes a Phase, and anything above STAGE/ZONE/AREA's own depth
just defaults to AREA (see `_BY_DEPTH.get(depth, AREA)` there) — reused
unmodified.
"""
import re

from .p6_schedule_import import _int, _locate_header, _num, _parse_date, _to_pct

_REQUIRED_HEADERS = ("activity id", "activity name", "start", "finish", "activity % complete")
_HEADER_SCAN_ROWS = 3

# Order matters: it IS the hierarchy, parent -> child. dec/sub_dec/nu are
# excluded — see module docstring, points 4 and 5.
_TAGS = ("pn", "con", "ar", "sar", "ph", "z", "p", "u", "lev", "dec", "sdec", "nu")
_TREE_TAGS = ("con", "ar", "sar", "ph", "z", "p", "u", "lev")  # pn dropped: redundant with project.name

_SEGMENT_RX = re.compile(
    r"^PN(\d+)-CON(\d+)-AR(\d+)-SAR(\d+)-PH(\d+)-Z(\d+)-P(\d+)-U(\d+)-LEV(\d+)-DEC(\d+)-SDEC(\d+)-NU(\d+)$",
    re.IGNORECASE,
)

_SAMPLE_SIZE = 30  # rows sampled to decide whether a sheet uses this scheme
_MATCH_RATIO = 0.6  # majority, not unanimous — a few malformed/legacy rows shouldn't disqualify a whole sheet


def parse_segmented_id(id_str: str):
    """Split one Activity ID into its 12 named segments, or None if it doesn't
    match the fixed pattern. Each value is the segment's int; 0 means
    "placeholder / not applicable here"."""
    m = _SEGMENT_RX.match(id_str.strip())
    if not m:
        return None
    return dict(zip(_TAGS, (int(g) for g in m.groups())))


def _tree_path(segments: dict) -> tuple:
    """Non-placeholder tree segments, in hierarchy order — e.g. {con:2, ar:3,
    sar:0, ph:4, ...} -> (("con", 2), ("ar", 3), ("ph", 4)). Two rows sharing a
    prefix share that ancestor node; SAR being 0 here just means this branch
    has no sub-area, not that the branch stops."""
    return tuple((tag, segments[tag]) for tag in _TREE_TAGS if segments[tag] != 0)


def _looks_like_segmented(rows, id_col) -> bool:
    seen = 0
    hits = 0
    for row in rows:
        v = row[id_col] if id_col < len(row) else None
        if not isinstance(v, str) or not v.strip():
            continue
        seen += 1
        if parse_segmented_id(v):
            hits += 1
        if seen >= _SAMPLE_SIZE:
            break
    return seen > 0 and hits / seen >= _MATCH_RATIO


def _new_group(name: str) -> dict:
    return {"name": name[:180], "children": [], "activities": [],
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


def parse_id_schedule_sheets(wb):
    """Return [{name, children, activities, start, finish}] built from a
    sheet's segmented Activity IDs, or None if no sheet matches this scheme.

    Every row is a leaf: there are no separate WBS rows to detect, so unlike
    parse_p6_schedule_sheets this samples the Activity ID column's own values
    to decide whether a sheet uses this scheme at all."""
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        located = _locate_header(rows)
        if not located:
            continue
        header_idx, cols = located
        id_c, name_c = cols["activity id"], cols["activity name"]
        data_rows = rows[header_idx + 1:]
        if not _looks_like_segmented(data_rows, id_c):
            continue

        start_c, finish_c = cols["start"], cols["finish"]
        pct_c = cols.get("activity % complete")
        dur_c = cols.get("original duration")
        rem_c = cols.get("remaining duration")
        float_c = cols.get("total float")
        cost_c = cols.get("budgeted material cost")
        ev_c = cols.get("earned value cost")

        by_path: dict[tuple, dict] = {}
        roots: list[dict] = []

        def node_for(path: tuple, segments: dict) -> dict:
            """Get-or-create the group node at `path`, creating any missing
            ancestors along the way so an out-of-order file still nests
            correctly."""
            if path in by_path:
                return by_path[path]
            parent_children = roots
            built = ()
            for tag, value in path:
                built = built + ((tag, value),)
                if built not in by_path:
                    label = f"{tag.upper()} {value:02d}" if value else tag.upper()
                    by_path[built] = _new_group(label)
                    parent_children.append(by_path[built])
                parent_children = by_path[built]["children"]
            return by_path[path]

        matched_any = False
        for row in data_rows:
            raw_id = row[id_c] if id_c < len(row) else None
            name = row[name_c] if name_c < len(row) else None
            if not isinstance(raw_id, str) or not isinstance(name, str) or not name.strip():
                continue
            segments = parse_segmented_id(raw_id)
            if segments is None:
                continue
            matched_any = True

            start = _parse_date(row[start_c]) if start_c < len(row) else None
            finish = _parse_date(row[finish_c]) if finish_c < len(row) else None
            pct = row[pct_c] if pct_c is not None and pct_c < len(row) else None
            task = {
                "code": f"NU{segments['nu']:03d}", "name": name.strip()[:200],
                "pct": _to_pct(pct), "start": start, "finish": finish,
                "budget": _num(row, cost_c), "earned_value": _num(row, ev_c),
                "float": _int(row, float_c), "duration": _int(row, dur_c),
                "remaining": _int(row, rem_c),
            }

            path = _tree_path(segments)
            if not path:
                # Every tree segment was a placeholder — nothing but PN/NU set.
                # Root it under a catch-all rather than dropping the row.
                path = (("uncategorized", 1),)
                if path not in by_path:
                    by_path[path] = _new_group("Uncategorized")
                    roots.append(by_path[path])
                by_path[path]["activities"].append(task)
                continue
            node_for(path, segments)["activities"].append(task)

        if not matched_any:
            continue
        for root in roots:
            _rollup_dates(root)
        return roots or None
    return None
