"use client";

// Small data-fetching hook giving the four required states (loading/error/empty/
// success) plus a manual reload. Pass a stable fetcher and dependency key.
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<State<T>>({ data: null, loading: true, error: null });

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  const load = useCallback(async (quiet: boolean) => {
    if (!quiet) setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await run();
      setState({ data, loading: false, error: null });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong.";
      // A background refresh that fails leaves what's on screen alone — the
      // caller that triggered it (a save, say) reports its own failure, and
      // blanking good data behind an error banner would be worse than stale.
      setState((s) => (quiet ? { ...s, loading: false } : { data: null, loading: false, error: message }));
    }
  }, [run]);

  /** Refetch with the loading state — callers render a spinner in place of
   * the content. Safe to pass straight to an onClick; it ignores arguments. */
  const reload = useCallback(() => load(false), [load]);

  /** Refetch WITHOUT flipping `loading`, so whatever is rendered stays
   * mounted. Use after a save: flipping `loading` unmounts the subtree, and
   * anything holding local state there (the layout editor's current page,
   * undo stacks, zoom) is destroyed just for saving (reported 2026-09-01). */
  const refresh = useCallback(() => load(true), [load]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { ...state, reload, refresh };
}
