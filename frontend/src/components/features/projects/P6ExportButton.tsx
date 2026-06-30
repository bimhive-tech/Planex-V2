"use client";

// P6 export button. For projects with a stored source workbook the file is large
// and built in the background: clicking prepares it, polls until ready, then
// downloads. For projects without one, the lightweight sheet downloads instantly.
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { api, ApiError } from "@/lib/api";
import { API_BASE } from "@/lib/constants";

type State = "idle" | "preparing" | "error";
const POLL_MS = 5000;

export function P6ExportButton({ projectId }: { projectId: string }) {
  const [state, setState] = useState<State>("idle");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  function download() {
    window.location.assign(`${API_BASE}/projects/${projectId}/export/p6/`);
  }

  function stopPolling() {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
  }

  function poll() {
    timer.current = setInterval(async () => {
      try {
        const s = await api.get<{ status: string; ready: boolean }>(`/projects/${projectId}/export/p6/status/`);
        if (s.ready) { stopPolling(); setState("idle"); download(); }
        else if (s.status === "error") { stopPolling(); setState("error"); }
      } catch {
        stopPolling();
        setState("error");
      }
    }, POLL_MS);
  }

  async function handleClick() {
    setState("preparing");
    try {
      const res = await api.post<{ mode: string }>(`/projects/${projectId}/export/p6/prepare/`);
      if (res.mode === "instant") { setState("idle"); download(); return; }
      poll(); // background build started
    } catch (err) {
      setState("error");
      if (!(err instanceof ApiError)) throw err;
    }
  }

  const label = state === "preparing" ? "Preparing…" : state === "error" ? "Export failed — retry" : "Export P6";

  return (
    <Button
      variant="secondary"
      size="sm"
      leadingIcon={<Icon name="download" size={15} />}
      onClick={handleClick}
      disabled={state === "preparing"}
    >
      {label}
    </Button>
  );
}
