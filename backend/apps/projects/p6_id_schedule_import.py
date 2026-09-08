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

A file whose codes DO fill every slot its legend declares is read by the
legend instead (see slot_depths/slot_path): which slot a segment sits in is
what says whether it is a place or the work done there, and each slot is
pinned to one depth for the whole file. The positional reading below is the
fallback for everything else.

The positional reading is deliberately content-based rather than a fixed
12-slot regex: the
legend sheet's own "0 vs omitted entirely" convention was inconsistent even
within ONE project's real file — Area/Sub-area/Part kept a literal "0"
placeholder in the string, while Level/Sub-discipline were dropped from it
entirely (10 dash-separated segments on every real row, not 12). A fixed-
position parser would have to special-case that exact combination and
would break the moment a different project's legend uses a different one
(the legend sheet is set up per-project, so it can vary). Matching by
content instead of position tolerates any combination without needing to
special-case each one.

Key Milestones (project start/end, handover dates, ...) carry NO Planex
Code at all in the first real export — see _milestone_group for the
indentation-based fallback used until the team adds one. The agreed
convention for when they do: a milestone row's Planex Code has "MS" as its
2nd segment, e.g. "MN(6)-MS-1" for a project-wide milestone, or
"MN(6)-MS-PH1-Z(A)-Building 15-1" to tie it to that building (segments
after "MS" follow the same placeholder-dropping rule as segment_path). See
is_milestone_code / milestone_scope_path.
"""
from .p6_schedule_import import _int, _leading_spaces, _locate_header, _num, _parse_date, _to_pct, _to_pct_optional

# Bare tag words that mean "this legend level isn't used on this row" when
# they appear with no distinguishing suffix (contrast "CON" alone vs "PH1").
_PLACEHOLDER_WORDS = {"pn", "con", "ar", "sub ar", "sar", "ph", "z", "p", "u", "lev", "dec", "sub dec", "sdec", "nu"}

_SAMPLE_SIZE = 30  # rows sampled to decide whether a sheet uses this scheme
_MATCH_RATIO = 0.6  # majority, not unanimous — a few malformed/legacy rows shouldn't disqualify a whole sheet
_MIN_SEGMENTS = 3  # project code + at least one real level + differentiator


# The legend's structural slots, split by what they describe. PN/CON/NU are
# the project code, the "construction" tag and the activity number — never
# scope levels.
#
# Places nest outermost-first in the order the legend declares them, so the
# ones a file actually uses fill ProjectScope's three place levels in that
# order (see slot_depths). The legend names seven places for three levels;
# a file using more than three folds the surplus into the innermost rather
# than dropping it.
_PLACE_SLOTS = ("ar", "sub ar", "sar", "ph", "z", "p", "u", "lev")
_WORK_SLOTS = ("dec", "sub dec", "sdec")
_PLACE_TYPES = ("stage", "zone", "area")


def slot_depths(codes, slots) -> dict:
    """Which scope level each legend slot fills IN THIS FILE — decided once
    from every code in the sheet, never per row.

    A legend declares far more slots than any one project uses (Cairo Airport
    fills 4 of its 12), and reading each row on its own put the same value at
    different depths depending on which of its neighbours happened to be
    filled: on the rows carrying both a Part and a Level, "L.2" was the second
    place; on the rows carrying only a Level it was the first. So L.2 came out
    a zone on some rows and a stage on others, and the report listed it as
    both. Deciding from the whole sheet keeps every slot at one depth.

    Returns {} when no code in the sheet fills the legend exactly — Mansoura's
    10 segments against a 12-slot legend keep the positional reading, since
    which two are missing is unknowable (see the module docstring)."""
    if not slots:
        return {}
    lower = [s.strip().lower() for s in slots]
    used, conforming = set(), False
    for code in codes:
        if not isinstance(code, str):
            continue
        parts = [p.strip() for p in code.strip().split("-")]
        if len(parts) != len(slots):
            continue
        conforming = True
        for value, slot in zip(parts, lower):
            if value and value != "0" and value.lower() not in _PLACEHOLDER_WORDS:
                used.add(slot)
    if not conforming:
        return {}

    places = [s for s in lower if s in _PLACE_SLOTS and s in used]
    depths = {s: _PLACE_TYPES[min(i, len(_PLACE_TYPES) - 1)] for i, s in enumerate(places)}
    depths.update({s: "phase" for s in lower if s in _WORK_SLOTS and s in used})
    return depths


def legend_slots(wb) -> list:
    """The ordered slot codes a workbook's own "Planex Code" sheet declares —
    ["PN", "CON", "AR", "SUB AR", "PH", "Z", "P", "U", "LEV", "DEC",
    "SUB DEC", "NU"] — or [] when the sheet is missing or unreadable.

    The legend is what gives a segment its meaning: "Civil" is a discipline
    because it sits in the DEC slot, not because of how many siblings on its
    row happen to be filled in."""
    for name in wb.sheetnames:
        if name.strip().lower() != "planex code":
            continue
        for row in wb[name].iter_rows(values_only=True):
            if row and isinstance(row[0], str) and row[0].strip().lower() == "code":
                return [str(c).strip() for c in row[1:] if c is not None and str(c).strip()]
    return []


def slot_path(code: str, slots: list, depths: dict) -> list:
    """[(name, scope_type)] for one code — its places outermost-first, then
    its work package. `depths` comes from slot_depths; [] when `code` doesn't
    fill the legend exactly.

    Only the DEEPEST work slot a row fills becomes the phase. A file's
    discipline slot classifies its work packages rather than containing them:
    across Cairo Airport's 492 rows no work package ever appears under two
    disciplines, so "Civil" above "Block works" is a second name for the same
    node, not a level of its own. Keeping both inserted a discipline between
    the place and the work, which made the per-unit progress table report
    "Civil" and "L.2A - Arch" as its units instead of the levels they are
    work on (2026-09-07)."""
    if not slots or not depths or not isinstance(code, str):
        return []
    parts = [p.strip() for p in code.strip().split("-")]
    if len(parts) != len(slots):
        return []
    out, work = [], None
    for value, slot in zip(parts, (s.strip().lower() for s in slots)):
        if not value or value == "0" or value.lower() in _PLACEHOLDER_WORDS:
            continue
        stype = depths.get(slot)
        if stype is None:
            continue
        if slot in _WORK_SLOTS:
            work = value          # the legend orders these too, so the last wins
        else:
            out.append((value, stype))
    if work is not None:
        out.append((work, "phase"))
    return out


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


def is_milestone_code(code: str) -> bool:
    """True when a Planex Code's own 2nd segment (right after the project
    code) is the "MS" tag, e.g. "MN(6)-MS-1" (project-wide) or
    "MN(6)-MS-PH1-Z(A)-Building 15-1" (tied to that building) — agreed with
    the team as the convention for coding the file's Key Milestones branch,
    which otherwise carries no Planex Code at all (see module docstring).
    Checked before segment_path() so these rows route to the Milestones
    panel instead of becoming a bogus "MS" branch in the scope tree."""
    if not isinstance(code, str):
        return False
    parts = [p.strip() for p in code.strip().split("-")]
    return len(parts) >= 2 and parts[1].strip().lower() == "ms"


def milestone_scope_path(code: str) -> tuple:
    """The zone/building segments (if any) between the "MS" tag and the
    trailing differentiator, e.g. ("PH1", "Z(A)", "Building 15") for a
    milestone tied to one building, or () for a project-wide one."""
    parts = [p.strip() for p in code.strip().split("-")]
    middle = parts[2:-1]
    return tuple(p for p in middle if p and p != "0" and p.lower() not in _PLACEHOLDER_WORDS)


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


def _new_group(name: str, stype: str | None = None) -> dict:
    # `stype` is set only when the file's own legend says what this segment is
    # (see slot_path); otherwise it stays None and the tree falls back to
    # typing by depth (p6_schedule_import's _BY_DEPTH).
    return {"name": name[:180] or "Uncategorized", "label": None, "children": [], "activities": [],
            "start": None, "finish": None, "pct": None, "schedule_pct": None, "stype": stype}


def _label_ancestors(by_path, path, heading_stack):
    """Best-effort human-readable label for each ancestor node in `path`,
    read from the file's own WBS heading text (e.g. "المرحلة الاولي (75
    عمارة)" for "PH1") via the indentation stack active at this row.

    Matched from the deepest level backward (path[-1] with heading_stack[-1],
    path[-2] with heading_stack[-2], ...): a placeholder segment dropped by
    segment_path only ever shortens the FRONT of the code path relative to
    the heading stack (the project code itself, and any bare tag wrapper
    like "CON" that still has its own WBS heading row but no distinguishing
    code) — confirmed against the real file, where the "مرحلة التنفيذ"
    wrapper heading has no code counterpart but sits at the front, not
    between two coded levels. A leftover heading at the front is simply
    unused; nothing here assumes every heading has a matching code segment.

    Only used for the positional reading. A legend-read file states its own
    nesting in the code, and its WBS headings need not agree: Cairo Airport
    nests them sub-discipline > level > part, the reverse of the order its
    legend declares those slots in, so lining the two up by position labelled
    the "P1" part "Civil Works" (2026-09-07). Its segments are already
    readable words ("P1", "L.2", "Steel Works"), so those rows go unlabelled
    rather than carrying a label naming something else.

    Purely cosmetic — sets `label`, never touches `name` (the matching key),
    so a heading text that changes or is missing on a later import cannot
    affect re-import correctness."""
    labels = [text for _, text in heading_stack]
    for i in range(1, len(path) + 1):
        node = by_path.get(path[:i])
        if node is None or node.get("label"):
            continue
        idx = len(labels) - (len(path) - i) - 1
        if 0 <= idx < len(labels):
            node["label"] = labels[idx][:180]


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
                    "pct": _to_pct(pct), "pct_raw": _to_pct_optional(pct), "start": start, "finish": finish,
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

        # The workbook's own "Planex Code" legend, if it has one — what makes
        # a segment's meaning positional-by-slot rather than by how many of
        # its siblings happen to be filled in.
        legend = legend_slots(wb)
        # One depth per slot for the WHOLE sheet, not per row — see slot_depths.
        slot_levels = slot_depths(
            (row[code_c] for row in data_rows if code_c < len(row)), legend)

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
        variance_c = cols.get("schedule variance")
        bl_dur_c = cols.get("bl project duration")
        actual_dur_c = cols.get("actual duration")
        spi_c = cols.get("schedule performance index")
        # The BASELINE's own view of how far along this should be — the figure
        # the client's reports quote as planned %. Read here rather than
        # recomputed from dates: the Start/Finish columns are the CURRENT
        # schedule, which has already absorbed the delay, so elapsed time
        # against them can never show a project as behind (2026-09-02).
        sched_pct_c = cols.get("schedule % complete")

        by_path: dict[tuple, dict] = {}
        roots: list[dict] = []

        def node_for(path: tuple, stypes: tuple = ()) -> dict:
            """Get-or-create the group node at `path`, creating any missing
            ancestors along the way so an out-of-order file still nests
            correctly. `stypes` pairs with `path` when the legend named each
            segment's level."""
            if path in by_path:
                return by_path[path]
            parent_children = roots
            built = ()
            for i, seg in enumerate(path):
                built = built + (seg,)
                if built not in by_path:
                    by_path[built] = _new_group(seg, stypes[i] if i < len(stypes) else None)
                    parent_children.append(by_path[built])
                parent_children = by_path[built]["children"]
            return by_path[path]

        matched_any = False
        coded_milestones: list[dict] = []
        # Tracks the WBS heading text currently "open" at each indentation
        # depth, purely to source human-readable labels (see _label_ancestors)
        # — independent of the code-driven tree being built below it.
        heading_stack: list[tuple[int, str]] = []
        for row in data_rows:
            raw_code = row[code_c] if code_c < len(row) else None
            act_id = row[id_c] if id_c < len(row) else None
            name = row[name_c] if name_c < len(row) else None
            if not isinstance(act_id, str) or not act_id.strip():
                continue

            if not (isinstance(name, str) and name.strip()):
                # A WBS heading row (no Activity Name) — just update the label
                # stack; it carries no Planex Code of its own either way.
                depth = _leading_spaces(act_id)
                while heading_stack and heading_stack[-1][0] >= depth:
                    heading_stack.pop()
                heading_stack.append((depth, act_id.strip()))
                continue

            if not isinstance(raw_code, str) or not raw_code.strip():
                continue

            start = _parse_date(row[start_c]) if start_c < len(row) else None
            finish = _parse_date(row[finish_c]) if finish_c < len(row) else None
            pct = row[pct_c] if pct_c is not None and pct_c < len(row) else None
            code = act_id.strip()[:60] if isinstance(act_id, str) and act_id.strip() else raw_code.strip()[:60]

            if is_milestone_code(raw_code):
                # Coded like the rest of the sheet ("MN(6)-MS-..."), rather
                # than the indentation-only fallback below — carries its own
                # zone/building path (if any) instead of relying on a raw-text
                # heading match, so it resolves to a real ProjectScope later.
                coded_milestones.append({
                    "code": code, "name": name.strip()[:200], "pct": _to_pct(pct),
                    "pct_raw": _to_pct_optional(pct),
                    "start": start, "finish": finish, "budget": None, "earned_value": None,
                    "float": None, "duration": None, "remaining": None,
                    "scope_path": milestone_scope_path(raw_code),
                })
                continue

            # The legend's own reading when the file fills every slot it
            # declares; the positional fallback otherwise (see slot_path).
            slotted = slot_path(raw_code, legend, slot_levels)
            if slotted:
                path = tuple(name for name, _ in slotted)
                stypes = tuple(st for _, st in slotted)
            else:
                path = tuple(segment_path(raw_code))
                stypes = ()
            if not path:
                continue
            matched_any = True

            task = {
                "code": code, "name": name.strip()[:200],
                "pct": _to_pct(pct), "start": start, "finish": finish,
                "budget": _num(row, cost_c), "earned_value": _num(row, ev_c),
                "float": _int(row, float_c), "duration": _int(row, dur_c),
                "remaining": _int(row, rem_c),
                "schedule_variance": _num(row, variance_c),
                "baseline_duration": _int(row, bl_dur_c), "actual_duration": _int(row, actual_dur_c),
                "spi": _num(row, spi_c),
                "schedule_pct": _to_pct_optional(row[sched_pct_c]) if sched_pct_c is not None
                                and sched_pct_c < len(row) else None,
            }
            node_for(path, stypes)["activities"].append(task)
            if not slotted:
                _label_ancestors(by_path, path, heading_stack)

        if not matched_any:
            continue

        if coded_milestones:
            # The team has adopted an "MS"-tagged code for Key Milestones —
            # prefer it over the indentation fallback below, since it's
            # explicit and gives each milestone a resolvable scope path.
            group = _new_group("Key Milestones")
            group["activities"] = coded_milestones
            roots.append(group)
        else:
            # The Key Milestones WBS branch carries no Planex Code at all yet
            # (see module docstring) — collected separately by indentation;
            # build_from_p6_schedule's existing milestone extraction then
            # routes it to the Milestones panel like it always has.
            milestones = _milestone_group(data_rows, id_c, name_c, start_c, finish_c, pct_c)
            if milestones:
                roots.append(milestones)

        for root in roots:
            _rollup_dates(root)
        return roots or None
    return None
