import { BOX_IDS, BOX_META, type BoxId, type BoxState, type RunEvent, type RunState } from "./types";

export function emptyBox(box_id: BoxId): BoxState {
  return {
    box_id,
    name: BOX_META[box_id].name,
    status: "starting",
    container_id: null,
    retry_count: 0,
    cpu_pct: null,
    mem_mb: null,
    steps: [],
    screenshots: [],
    approval: null,
    decision: null,
    receipt: null,
    bugs: [],
    vision_summary: null,
    vision_step: null,
    summary: null,
  };
}

export function newRun(run_id: string, mode: RunState["mode"], url: string, mock = false): RunState {
  return {
    run_id,
    status: "running",
    mode,
    url,
    boxes: { box1: emptyBox("box1"), box2: emptyBox("box2"), box3: emptyBox("box3") },
    verdict: null,
    headline: null,
    fix_prompt: null,
    annotated_box_id: null,
    annotated_step: null,
    connection: "connecting",
    mock,
  };
}

const TERMINAL = new Set(["completed", "blocked", "contained", "failed"]);

function patchBox(run: RunState, id: BoxId, patch: (b: BoxState) => Partial<BoxState>): RunState {
  const b = run.boxes[id];
  return { ...run, boxes: { ...run.boxes, [id]: { ...b, ...patch(b) } } };
}

export type Action =
  | { kind: "reset"; run: RunState | null }
  | { kind: "event"; event: RunEvent }
  | { kind: "connection"; connection: RunState["connection"] }
  | { kind: "snapshot"; snapshot: Record<string, unknown> }
  | { kind: "decision"; box_id: BoxId; decision: "approve" | "block" };

export function reducer(run: RunState | null, action: Action): RunState | null {
  if (action.kind === "reset") return action.run;
  if (!run) return run;
  switch (action.kind) {
    case "connection":
      return { ...run, connection: action.connection };
    case "decision":
      return patchBox(run, action.box_id, (b) => ({
        decision: action.decision,
        approval: null,
        status: TERMINAL.has(b.status) ? b.status : action.decision === "approve" ? "running" : "blocked",
      }));
    case "snapshot":
      return applySnapshot(run, action.snapshot);
    case "event":
      return applyEvent(run, action.event);
  }
}

function applyEvent(run: RunState, e: RunEvent): RunState {
  if (e.run_id && e.run_id !== run.run_id) return run;
  const id = e.box_id;
  switch (e.type) {
    case "box_started":
      if (!id) return run;
      return patchBox(run, id, (b) => ({
        container_id: e.container_id ?? b.container_id,
        status: TERMINAL.has(b.status) ? b.status : "running",
      }));

    case "step_update":
      if (!id) return run;
      return patchBox(run, id, (b) => ({
        status: b.status === "starting" ? "running" : b.status,
        retry_count: e.retry_count ?? b.retry_count,
        cpu_pct: e.cpu_pct ?? b.cpu_pct,
        mem_mb: e.mem_mb ?? b.mem_mb,
        steps: [
          ...b.steps,
          {
            step: e.step,
            ts: e.ts,
            action: e.action,
            selector: e.selector,
            ok: e.ok,
            thought: e.thought,
            log: e.log,
            page_url: e.page_url,
          },
        ].slice(-200),
      }));

    // TODO(spec): additive event for metering between steps. Not in Section 6; harmless if never sent.
    case "box_stats":
      if (!id) return run;
      return patchBox(run, id, (b) => ({ cpu_pct: e.cpu_pct ?? b.cpu_pct, mem_mb: e.mem_mb ?? b.mem_mb }));

    case "screenshot": {
      if (!id) return run;
      const src: string | undefined = e.data_base64
        ? `data:${e.content_type ?? "image/png"};base64,${e.data_base64}`
        : e.url;
      if (!src) return run;
      return patchBox(run, id, (b) => ({
        screenshots: [
          ...b.screenshots.filter((s) => s.step !== e.step),
          { step: e.step, src, width: e.width ?? 0, height: e.height ?? 0 },
        ].slice(-24),
      }));
    }

    case "approval_required":
      if (!id) return run;
      return patchBox(run, id, () => ({
        status: "waiting_for_approval",
        decision: null,
        approval: {
          action: e.action,
          selector: e.selector,
          page_url: e.page_url,
          reason: e.reason,
        },
      }));

    // TODO(spec): Section 6.3 has no event for Box 2 audit results. We accept this additive
    // `vision_audit` event {box_id, step, summary, bugs[]} and also read bugs from the GET snapshot.
    case "vision_audit":
      if (!id) return run;
      return patchBox(run, id, () => ({
        bugs: Array.isArray(e.bugs) ? e.bugs : [],
        vision_summary: e.summary ?? null,
        vision_step: e.step ?? null,
      }));

    case "containment_triggered": {
      const target = (id ?? "box3") as BoxId;
      const { type: _t, ts: _ts, ...receipt } = e;
      void _t;
      void _ts;
      return patchBox(run, target, (b) => ({
        status: "contained",
        approval: null,
        receipt: receipt as unknown as BoxState["receipt"],
        cpu_pct: e.peak_cpu_pct ?? b.cpu_pct,
        mem_mb: e.peak_mem_mb ?? b.mem_mb,
      }));
    }

    case "box_finished":
      if (!id) return run;
      return patchBox(run, id, (b) => ({
        status: b.status === "contained" ? "contained" : e.status,
        summary: e.summary ?? b.summary,
        approval: null,
      }));

    case "run_verdict":
      return {
        ...run,
        status: "completed",
        verdict: e.verdict,
        headline: e.headline ?? null,
        fix_prompt: e.fix_prompt ?? null,
        annotated_box_id: e.annotated_screenshot_box_id ?? null,
        annotated_step: e.annotated_screenshot_step ?? null,
      };

    case "run_failed":
      return { ...run, status: "failed" };

    default:
      return run;
  }
}

/** Snapshots can be stale relative to WS events: never move a box backwards. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mergeStatus(b: BoxState, sb: any): BoxState["status"] {
  const incoming = sb.status as BoxState["status"] | undefined;
  if (!incoming || incoming === b.status) return b.status;
  if (TERMINAL.has(b.status)) return b.status;
  if (b.status === "waiting_for_approval" && !TERMINAL.has(incoming) && !sb.approval?.decision) return b.status;
  return incoming;
}

/** Merge a GET /api/runs/{id} snapshot (Section 6.5). Shapes beyond the spec example are best effort. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function applySnapshot(run: RunState, s: any): RunState {
  let next: RunState = {
    ...run,
    status: run.status === "running" ? s.status ?? run.status : run.status,
    url: s.url ?? run.url,
    verdict: s.verdict ?? run.verdict,
    headline: s.headline ?? run.headline,
    fix_prompt: s.fix_prompt ?? run.fix_prompt,
    annotated_box_id: s.annotated_screenshot_box_id ?? run.annotated_box_id,
    annotated_step: s.annotated_screenshot_step ?? run.annotated_step,
  };
  for (const id of BOX_IDS) {
    const sb = s.boxes?.[id];
    if (!sb || Object.keys(sb).length === 0) continue;
    next = patchBox(next, id, (b) => ({
      status: mergeStatus(b, sb),
      retry_count: sb.retry_count ?? b.retry_count,
      container_id: sb.container_id ?? b.container_id,
      steps: Array.isArray(sb.steps) && sb.steps.length >= b.steps.length ? sb.steps : b.steps,
      screenshots:
        Array.isArray(sb.screenshots) && sb.screenshots.length > b.screenshots.length
          ? // TODO(spec): snapshot screenshot entry shape is unspecified; accept {step,url|data_base64,width,height}.
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            sb.screenshots.map((x: any) => ({
              step: x.step,
              src: x.data_base64 ? `data:${x.content_type ?? "image/png"};base64,${x.data_base64}` : x.url,
              width: x.width ?? 0,
              height: x.height ?? 0,
            }))
          : b.screenshots,
      approval:
        TERMINAL.has(b.status)
          ? null
          : sb.approval?.required && !sb.approval.decision
          ? b.approval ?? { action: "click", selector: "", page_url: "", reason: sb.approval.reason ?? "" }
          : sb.approval?.decision
            ? null
            : b.approval,
      decision: sb.approval?.decision ?? b.decision,
      receipt: sb.containment_receipt ?? b.receipt,
      bugs: Array.isArray(sb.bugs) ? sb.bugs : b.bugs,
      vision_summary: sb.vision_summary ?? b.vision_summary,
      summary: sb.summary ?? b.summary,
    }));
  }
  return next;
}

export function isBoxDone(b: BoxState) {
  return TERMINAL.has(b.status);
}
