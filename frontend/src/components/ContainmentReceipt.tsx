import type { ContainmentReceipt as Receipt } from "../lib/types";

const REASON: Record<Receipt["trigger_reason"], string> = {
  prompt_injection_detected: "Prompt injection detected",
  cpu_limit_exceeded: "CPU limit exceeded",
  oom_killed: "Out of memory",
  timeout: "Wall-clock timeout",
};

export function ContainmentReceipt({ r }: { r: Receipt }) {
  // Defensive: the receipt comes over the wire; a missing field must never blank the page.
  const num = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);
  const cid = String(r.container_id ?? "unknown");
  const when = r.timestamp_iso ? new Date(r.timestamp_iso) : null;
  const rows: [string, React.ReactNode, boolean?][] = [
    ["trigger_reason", REASON[r.trigger_reason] ?? String(r.trigger_reason ?? "unknown")],
    ["signal", r.signal ?? "SIGKILL"],
    ["elapsed_ms", `${num(r.elapsed_ms)} ms`],
    ["peak_cpu_pct", `${num(r.peak_cpu_pct).toFixed(1)}%`],
    ["peak_mem_mb", `${num(r.peak_mem_mb).toFixed(1)} MB`],
    ["secrets_exposed", String(r.secrets_exposed ?? "?"), r.secrets_exposed === 0],
    ["host_impact", r.host_impact ?? "?", r.host_impact === "none"],
    ["container_destroyed", String(r.container_destroyed), r.container_destroyed],
    ["container_id", <code key="c">{cid.slice(0, 12)}</code>],
    ["timestamp", when && !isNaN(when.getTime()) ? when.toLocaleTimeString() : "--"],
  ];
  return (
    <section className="receipt" aria-label="Containment Receipt">
      <h3>Containment Receipt</h3>
      <p className="receipt-lede">Box killed and wiped. Other boxes keep running.</p>
      <dl>
        {rows.map(([k, v, good]) => (
          <div key={k} className={good ? "good" : undefined}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {r.notes && <p className="receipt-notes">{r.notes}</p>}
    </section>
  );
}
