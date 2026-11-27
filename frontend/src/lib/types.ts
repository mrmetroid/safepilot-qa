// Contracts mirror BUILD_SPEC.md Sections 3.6, 4.6 and 6. Keep additive.

export type BoxId = "box1" | "box2" | "box3";
export const BOX_IDS: BoxId[] = ["box1", "box2", "box3"];

export const BOX_META: Record<BoxId, { name: string; blurb: string; viewport: string }> = {
  box1: { name: "Happy Path", blurb: "Sign up, cart, checkout. Waits for you before submit.", viewport: "1280x800" },
  box2: { name: "Mobile Vision Check", blurb: "390x844 screenshot audited by Vultr vision.", viewport: "390x844" },
  box3: { name: "Chaos Gremlin", blurb: "Pokes promo and advanced paths. Expected to get contained.", viewport: "1280x800" },
};

export type Verdict = "DO NOT SHIP" | "SHIP IT";

export type BoxStatus =
  | "starting"
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "blocked"
  | "contained"
  | "failed";

export interface ContainmentReceipt {
  container_id: string;
  box_name: string;
  box_id: BoxId;
  run_id: string;
  trigger_reason: "cpu_limit_exceeded" | "timeout" | "prompt_injection_detected" | "oom_killed";
  signal: string;
  elapsed_ms: number;
  peak_cpu_pct: number;
  peak_mem_mb: number;
  secrets_exposed: number;
  host_impact: string;
  container_destroyed: boolean;
  timestamp_iso: string;
  notes?: string;
}

export interface VisionBug {
  id: string;
  severity: "critical" | "major" | "minor";
  title: string;
  description: string;
  bbox: [number, number, number, number];
}

export interface StepEntry {
  step: number;
  ts: string;
  action?: string;
  selector?: string;
  ok?: boolean;
  thought?: string;
  log?: string;
  page_url?: string;
}

export interface Shot {
  step: number;
  src: string;
  width: number;
  height: number;
}

export interface ApprovalRequest {
  action: string;
  selector: string;
  page_url: string;
  reason: string;
}

export interface BoxState {
  box_id: BoxId;
  name: string;
  status: BoxStatus;
  container_id: string | null;
  retry_count: number;
  cpu_pct: number | null;
  mem_mb: number | null;
  steps: StepEntry[];
  screenshots: Shot[];
  approval: ApprovalRequest | null;
  decision: "approve" | "block" | null;
  receipt: ContainmentReceipt | null;
  bugs: VisionBug[];
  vision_summary: string | null;
  vision_step: number | null;
  summary: string | null;
}

export interface RunState {
  run_id: string;
  status: "running" | "completed" | "failed";
  mode: "custom" | "adversarial_preset";
  url: string;
  boxes: Record<BoxId, BoxState>;
  verdict: Verdict | null;
  headline: string | null;
  fix_prompt: string | null;
  annotated_box_id: BoxId | null;
  annotated_step: number | null;
  connection: "connecting" | "live" | "reconnecting" | "closed";
  mock: boolean;
}

export interface HealthResponse {
  ok: boolean;
  control_plane?: string;
  docker?: string;
  inference?: string;
  inference_model?: string;
  sandbox_image?: string;
  error?: string;
  [k: string]: unknown;
}

export interface CreateRunResponse {
  run_id: string;
  status: string;
  mode: RunState["mode"];
  url: string;
  boxes: { box_id: BoxId; name: string; status: BoxStatus }[];
  ws_url: string;
}

// Any WS event. Fields vary by `type`.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type RunEvent = { type: string; run_id: string; ts: string; box_id?: BoxId; [k: string]: any };
