"""Generic counterpart to apps.projects.p6_schedule_import: builds the exact
same intermediate tree shape (so apps.projects.p6_schedule_import functions
can process it unchanged), but the column layout and hierarchy signal come
from an AI-inferred rule instead of the fixed P6 template's column names.

This is what makes AI-driven import scale to files of any size: describing a
file's *shape* (a few hundred tokens) doesn't grow with the file, unlike
asking the model to re-emit every row as a classified tree (bounded by the
model's own output-token limit long before Planex's own row counts are)."""
import datetime
import re

_DATE_RX = re.compile(r"(\d{1,2})[-/]([A-Za-z]{3}|\d{1,2})[-/](\d{2,4})")


def _leading_spaces(s: str) -> int:
    return len(s) - len(s.lstrip(" "))


def _parse_generic_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        m = _DATE_RX.search(v)
        if not m:
            return None
        day, mon, year = m.groups()
        year_fmt = "%Y" if len(year) == 4 else "%y"
        mon_fmt = "%b" if mon.isalpha() else "%m"
        try:
            return datetime.datetime.strptime(f"{day}-{mon}-{year}", f"%d-{mon_fmt}-{year_fmt}").date()
        except ValueError:
            return None
    return None


def _num(row, col):
    if col is None or col >= len(row):
        return None
    v = row[col]
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _to_pct(v):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return 0.0
    pct = v * 100 if v <= 1.0001 else v
    return max(0.0, min(100.0, round(pct, 2)))


def build_tree_from_rule(wb, rule: dict) -> list:
    """Walk one sheet applying an AI-inferred rule, producing the exact node
    shape build_from_p6_schedule expects: {name, children, activities, start,
    finish, pct, schedule_pct}, activities as {code, name, pct, start,
    finish, budget, earned_value, float, duration, remaining}.

    Same convention as the real P6 export: one column ("hierarchy_text")
    carries WBS/group text indented with leading spaces per level; a leaf
    activity row is one that ALSO has a value in a separate "name" column
    (headings leave it blank). Same stack-based depth grouping as the P6
    parser — not a coincidence, it's the same tree shape by design."""
    sheet_name = rule.get("sheet_name")
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.worksheets[0]
    cols = rule["columns"]
    hierarchy_c = cols["hierarchy_text"]
    name_c = cols["name"]
    start_c = cols.get("start")
    finish_c = cols.get("finish")
    pct_c = cols.get("progress_percent")
    weight_c = cols.get("weight")
    header_row_index = rule.get("header_row_index", 0)

    data_rows = ws.iter_rows(values_only=True, min_row=header_row_index + 2)

    roots, stack = [], []  # stack of (depth, node)
    for row in data_rows:
        h = row[hierarchy_c] if hierarchy_c < len(row) else None
        if h is None or (isinstance(h, str) and not h.strip()):
            continue
        h_str = str(h)
        n = row[name_c] if name_c is not None and name_c < len(row) else None
        start = _parse_generic_date(row[start_c]) if start_c is not None and start_c < len(row) else None
        finish = _parse_generic_date(row[finish_c]) if finish_c is not None and finish_c < len(row) else None

        if isinstance(n, str) and n.strip():  # leaf activity row
            if not stack:
                continue  # no parent WBS group to root it under
            pct = row[pct_c] if pct_c is not None and pct_c < len(row) else None
            stack[-1][1]["activities"].append({
                "code": h_str.strip()[:60], "name": n.strip()[:200],
                "pct": _to_pct(pct), "start": start, "finish": finish,
                "budget": _num(row, weight_c), "earned_value": None,
                "float": None, "duration": None, "remaining": None,
            })
            continue

        depth = _leading_spaces(h_str)
        node = {"name": h_str.strip()[:180], "children": [], "activities": [],
                "start": start, "finish": finish, "pct": None, "schedule_pct": None}
        while stack and stack[-1][0] >= depth:
            stack.pop()
        (stack[-1][1]["children"] if stack else roots).append(node)
        stack.append((depth, node))
    return roots


def tree_to_json_safe(nodes: list) -> list:
    """Dates aren't JSON-serializable — this is how the tree gets persisted in
    a proposal (and read back via tree_from_json_safe before commit)."""
    out = []
    for n in nodes:
        out.append({
            "name": n["name"],
            "start": n["start"].isoformat() if n.get("start") else None,
            "finish": n["finish"].isoformat() if n.get("finish") else None,
            "pct": n.get("pct"), "schedule_pct": n.get("schedule_pct"),
            "activities": [
                {**a,
                 "start": a["start"].isoformat() if a.get("start") else None,
                 "finish": a["finish"].isoformat() if a.get("finish") else None}
                for a in n["activities"]
            ],
            "children": tree_to_json_safe(n["children"]),
        })
    return out


def tree_from_json_safe(nodes: list) -> list:
    out = []
    for n in nodes:
        out.append({
            "name": n["name"],
            "start": datetime.date.fromisoformat(n["start"]) if n.get("start") else None,
            "finish": datetime.date.fromisoformat(n["finish"]) if n.get("finish") else None,
            "pct": n.get("pct"), "schedule_pct": n.get("schedule_pct"),
            "activities": [
                {**a,
                 "start": datetime.date.fromisoformat(a["start"]) if a.get("start") else None,
                 "finish": datetime.date.fromisoformat(a["finish"]) if a.get("finish") else None}
                for a in n["activities"]
            ],
            "children": tree_from_json_safe(n["children"]),
        })
    return out


def summarize_tree(roots: list) -> dict:
    """Dry-run counts for the confirmation card — reuses the exact same pure
    milestone-extraction/pruning/weight-key logic build_from_p6_schedule uses,
    on a copy, so the preview numbers match what committing will actually do."""
    import copy

    from apps.projects.p6_schedule_import import _entry_nodes, _extract_milestones, _prune_empty, _weight_key

    roots_copy = copy.deepcopy(roots)
    milestone_tasks = _extract_milestones(roots_copy)
    _prune_empty(roots_copy)
    entries = _entry_nodes(roots_copy)
    weight_key = _weight_key(roots_copy)

    def count(nodes):
        scopes = activities = 0
        for node in nodes:
            scopes += 1
            activities += len(node["activities"])
            sub_scopes, sub_activities = count(node["children"])
            scopes += sub_scopes
            activities += sub_activities
        return scopes, activities

    scopes, activities = count(entries)
    return {
        "scopes": scopes, "activities": activities,
        "milestones": len(milestone_tasks), "weighted_by": weight_key or "equal",
    }
