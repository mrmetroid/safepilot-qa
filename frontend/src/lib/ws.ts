import type { RunEvent } from "./types";

export interface RunSocketHandlers {
  onEvent: (e: RunEvent) => void;
  onStatus: (s: "connecting" | "live" | "reconnecting" | "closed") => void;
  /** Called after every (re)connect so the caller can hydrate from GET /api/runs/{id}. */
  onOpen?: () => void;
  shouldReconnect: () => boolean;
}

/** Opens WS /ws/runs/{run_id} on the same host, with simple capped reconnects. Returns a closer. */
export function openRunSocket(wsPath: string, h: RunSocketHandlers): () => void {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = wsPath.startsWith("ws") ? wsPath : `${proto}//${location.host}${wsPath}`;
  let ws: WebSocket | null = null;
  let attempts = 0;
  let stopped = false;
  let timer: number | undefined;

  const connect = () => {
    h.onStatus(attempts === 0 ? "connecting" : "reconnecting");
    ws = new WebSocket(url);
    ws.onopen = () => {
      attempts = 0;
      h.onStatus("live");
      h.onOpen?.();
    };
    ws.onmessage = (m) => {
      try {
        h.onEvent(JSON.parse(m.data));
      } catch {
        /* ignore non-JSON frames */
      }
    };
    ws.onclose = () => {
      if (stopped) return;
      if (h.shouldReconnect() && attempts < 8) {
        attempts += 1;
        h.onStatus("reconnecting");
        timer = window.setTimeout(connect, Math.min(500 * 2 ** attempts, 5000));
      } else {
        h.onStatus("closed");
      }
    };
  };
  connect();

  return () => {
    stopped = true;
    window.clearTimeout(timer);
    ws?.close();
  };
}
