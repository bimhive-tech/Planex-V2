"use client";

// Lazy, hierarchical scope picker for the report: Zone → Subzone → Phase → Task.
// Tick a node to include it (and everything under it). An ancestor being ticked
// implicitly includes its descendants (shown checked + disabled).
import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { api } from "@/lib/api";
import styles from "./scopeTree.module.css";

interface Node {
  id: string;
  name: string;
  type: string; // zone | area | building | phase | task
  has_children: boolean;
}

interface TreeProps {
  projectId: string;
  selectedIds: string[];
  onToggle: (id: string) => void;
  canManage: boolean;
}

export function ScopeTree({ projectId, selectedIds, onToggle, canManage }: TreeProps) {
  const [roots, setRoots] = useState<Node[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    api.get<Node[]>(`/projects/${projectId}/scope-tree/`)
      .then((d) => alive && setRoots(d))
      .catch(() => alive && setError(true));
    return () => { alive = false; };
  }, [projectId]);

  if (error) return <p className={styles.msg}>Couldn&apos;t load the project structure.</p>;
  if (!roots) return <p className={styles.msg}>Loading structure…</p>;
  if (roots.length === 0) return <p className={styles.msg}>This project has no structure yet.</p>;

  return (
    <ul className={styles.tree}>
      {roots.map((n) => (
        <ScopeNode key={n.id} node={n} projectId={projectId} selectedIds={selectedIds}
          onToggle={onToggle} canManage={canManage} ancestorSelected={false} />
      ))}
    </ul>
  );
}

function ScopeNode({ node, projectId, selectedIds, onToggle, canManage, ancestorSelected }: {
  node: Node; projectId: string; selectedIds: string[]; onToggle: (id: string) => void;
  canManage: boolean; ancestorSelected: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<Node[] | null>(null);
  const [loading, setLoading] = useState(false);

  const directlyChecked = selectedIds.includes(node.id);
  const checked = ancestorSelected || directlyChecked;

  async function toggleOpen() {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (children === null && node.has_children) {
      setLoading(true);
      try {
        if (node.type === "phase") {
          const acts = await api.get<{ id: string; name: string }[]>(`/projects/${projectId}/scopes/${node.id}/activities/`);
          setChildren(acts.map((a) => ({ id: a.id, name: a.name, type: "task", has_children: false })));
        } else {
          setChildren(await api.get<Node[]>(`/projects/${projectId}/scope-tree/?parent=${node.id}`));
        }
      } catch {
        setChildren([]);
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <li className={styles.node}>
      <div className={styles.row}>
        {node.has_children ? (
          <button type="button" className={styles.caret} onClick={toggleOpen} aria-label={open ? "Collapse" : "Expand"}>
            <Icon name="chevronDown" size={14} style={{ transform: open ? "none" : "rotate(-90deg)" }} />
          </button>
        ) : (
          <span className={styles.caretSpace} />
        )}
        <label className={styles.label}>
          <input type="checkbox" checked={checked} disabled={!canManage || ancestorSelected}
            onChange={() => onToggle(node.id)} />
          <span>{node.name}</span>
          <span className={styles.type}>{node.type}</span>
        </label>
      </div>
      {open && (
        loading ? <p className={styles.msg}>Loading…</p> : (
          <ul className={styles.children}>
            {(children ?? []).map((c) => (
              <ScopeNode key={c.id} node={c} projectId={projectId} selectedIds={selectedIds}
                onToggle={onToggle} canManage={canManage} ancestorSelected={checked} />
            ))}
          </ul>
        )
      )}
    </li>
  );
}
