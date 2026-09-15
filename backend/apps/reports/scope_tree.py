"""A project's scope tree as the report reads it, with empty Planex-code
levels made transparent (register E2).

A Planex-coded schedule keeps every level its code declares — "No area ›
No sub-area › No phase › No zone › Part 2 › No unit › Level 2A › MEP" — so
the Schedule tab reads like the code. The report must not print those empty
levels as rows or prefix names with them: to the report a placeholder is not
there, its children are its parent's children, and a name is told apart by
the nearest level that names something. Built once per query from the rows
the caller already loaded.
"""


class ScopeTree:
    """`rows`: (id, parent_id, is_placeholder, sort_order, name) per scope."""

    def __init__(self, rows):
        self.parent, self.empty, self.children, self._key = {}, set(), {}, {}
        for sid, pid, placeholder, order, name in rows:
            sid, pid = str(sid), (str(pid) if pid else None)
            self.parent[sid] = pid
            self._key[sid] = (order or 0, name or "")
            if placeholder:
                self.empty.add(sid)
            if pid:
                self.children.setdefault(pid, []).append(sid)
        for kids in self.children.values():
            kids.sort(key=lambda c: self._key[c])

    @classmethod
    def for_scopes(cls, scopes):
        """From a ProjectScope queryset."""
        return cls(scopes.values_list("id", "parent_id", "is_placeholder", "sort_order", "name"))

    def is_empty(self, sid) -> bool:
        return str(sid) in self.empty

    def real_children(self, sid):
        """`sid`'s children in order, with every placeholder replaced by its
        own real children."""
        out = []
        for child in self.children.get(str(sid), []):
            out.extend(self.real_children(child) if child in self.empty else [child])
        return out

    def real_ancestor(self, sid):
        """The nearest ancestor of `sid` that is not a placeholder, or None."""
        seen, cur = set(), self.parent.get(str(sid))
        while cur is not None and cur not in seen:
            if cur not in self.empty:
                return cur
            seen.add(cur)
            cur = self.parent.get(cur)
        return None

    def order(self):
        """{id: position} in the order the Schedule tree reads, top to bottom.
        Sorting by each scope's own sort_order alone mixed levels from
        different branches, since that number only orders siblings."""
        out, roots = {}, sorted((s for s, p in self.parent.items() if p is None), key=lambda s: self._key[s])
        stack = list(reversed(roots))
        while stack:
            node = stack.pop()
            if node in out:
                continue
            out[node] = len(out)
            stack.extend(reversed(self.children.get(node, [])))
        return out
