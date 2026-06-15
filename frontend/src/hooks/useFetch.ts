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

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await run();
      setState({ data, loading: false, error: null });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong.";
      setState({ data: null, loading: false, error: message });
    }
  }, [run]);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: load };
}
