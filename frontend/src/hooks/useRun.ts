import { useCallback, useEffect, useRef, useState } from "react";
import { api, errMsg, RunEvent, RunResult } from "../api";

export type RunMode = "chat" | "architecture" | "review" | "testing" | "report";

/** Starts a backend agent run and streams its REAL events over Server-Sent Events. */
export function useRun() {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => () => esRef.current?.close(), []);

  const start = useCallback(async (repoId: string, mode: RunMode, message = ""): Promise<RunResult | null> => {
    esRef.current?.close();
    setEvents([]); setResult(null); setError(null); setRunning(true);
    try {
      const { data } = await api.post(`/repos/${repoId}/runs`, { mode, message });
      const runId: string = data.run_id;
      return await new Promise<RunResult | null>((resolve) => {
        const es = new EventSource(`/api/runs/${runId}/events`);
        esRef.current = es;
        const finish = async () => {
          es.close();
          try {
            const r = await api.get(`/runs/${runId}`);
            if (r.data.status === "failed") setError(r.data.result?.error ?? "Run failed");
            setResult(r.data.result?.answer !== undefined ? r.data.result : null);
            setRunning(false);
            resolve(r.data.result ?? null);
          } catch (e) { setError(errMsg(e)); setRunning(false); resolve(null); }
        };
        es.addEventListener("agent_event", (m) => {
          const ev: RunEvent = JSON.parse((m as MessageEvent).data);
          setEvents((p) => [...p, ev]);
          if (ev.type === "run_finished") finish();
        });
        es.onerror = () => { if (es.readyState === EventSource.CLOSED) finish(); };
      });
    } catch (e) { setError(errMsg(e)); setRunning(false); return null; }
  }, []);

  return { events, running, result, error, start, setEvents };
}
