"use client";

// Header global search: debounced lookup across projects + activities, with a
// results dropdown that navigates on select. Tenant/permission scoped server-side.
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Icon } from "@/components/ui/Icon";
import { useClickOutside } from "@/hooks/useClickOutside";
import { api } from "@/lib/api";
import type { SearchResponse } from "@/types/search";
import styles from "./GlobalSearch.module.css";

const DEBOUNCE_MS = 300;
const MIN_LEN = 2;

export function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);

  useEffect(() => {
    const q = query.trim();
    if (q.length < MIN_LEN) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        setData(await api.get<SearchResponse>(`/search/?q=${encodeURIComponent(q)}`));
        setOpen(true);
      } catch {
        setData(null);
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  function go(href: string) {
    setOpen(false);
    setQuery("");
    setData(null);
    router.push(href);
  }

  const hasResults = data && (data.projects.length > 0 || data.activities.length > 0);
  const showPanel = open && query.trim().length >= MIN_LEN;

  return (
    <div className={styles.wrap} ref={ref}>
      <div className={styles.box}>
        <Icon name="search" size={18} />
        <input
          className={styles.input}
          type="search"
          placeholder="Search projects, activities…"
          aria-label="Search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => query.trim().length >= MIN_LEN && setOpen(true)}
        />
      </div>

      {showPanel && (
        <div className={styles.panel} role="listbox">
          {loading && !data ? (
            <p className={styles.hint}>Searching…</p>
          ) : !hasResults ? (
            <p className={styles.hint}>No matches for “{query.trim()}”.</p>
          ) : (
            <>
              {data!.projects.length > 0 && (
                <div className={styles.group}>
                  <span className={styles.groupLabel}>Projects</span>
                  {data!.projects.map((p) => (
                    <button key={p.id} className={styles.item} onClick={() => go(`/projects/${p.id}`)}>
                      <Icon name="projects" size={15} />
                      <span className={styles.itemMain}>{p.name}</span>
                      {p.location && <span className={styles.itemSub}>{p.location}</span>}
                    </button>
                  ))}
                </div>
              )}
              {data!.activities.length > 0 && (
                <div className={styles.group}>
                  <span className={styles.groupLabel}>Activities</span>
                  {data!.activities.map((a) => (
                    <button key={a.id} className={styles.item} onClick={() => go(`/projects/${a.project_id}`)}>
                      <Icon name="list" size={15} />
                      <span className={styles.itemMain}>{a.name}</span>
                      <span className={styles.itemSub}>{a.project_name}</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
