import { useEffect, useRef } from "react";
import { BOX_META, type BoxState, type Shot } from "../lib/types";
import { ContainmentReceipt } from "./ContainmentReceipt";
import { ScreenshotFilmstrip } from "./ScreenshotFilmstrip";

const STATUS_LABEL: Record<BoxState["status"], string> = {
  starting: "Starting",
  running: "Running",
  waiting_for_approval: "Waiting for you",
  completed: "Completed",
  blocked: "Blocked",
  contained: "Contained",
  failed: "Failed",
};

function Meter({ label, value, max, unit }: { label: string; value: number | null; max: number; unit: string }) {
  const pct = value == null ? 0 : Math.min(100, (value / max) * 100);
  const level = pct > 85 ? "hot" : pct > 60 ? "warm" : "ok";
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <span>{value == null ? "--" : `${value.toFixed(0)}${unit}`}</span>
      </div>
      <div className="meter-track">
        <div className={`meter-fill meter-${level}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function BoxCard({ box, index, onOpenShot }: { box: BoxState; index: number; onOpenShot: (s: Shot) => void }) {
  const logRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [box.steps.length]);

  const meta = BOX_META[box.box_id];
  return (
    <article className={`box status-${box.status}`}>
      <header className="box-head">
        <div>
          <div className="box-kicker">Box {index + 1} · {meta.viewport}</div>
          <h2>{box.name}</h2>
        </div>
        <span className={`pill pill-${box.status}`}>{STATUS_LABEL[box.status] ?? box.status}</span>
      </header>
      <p className="box-blurb">{meta.blurb}</p>

      <div className="box-stats">
        <Meter label="CPU" value={box.cpu_pct} max={100} unit="%" />
        <Meter label="RAM" value={box.mem_mb} max={512} unit=" MB" />
        <div className="retry">
          <span>Retries</span>
          <strong>{box.retry_count}</strong>
        </div>
      </div>

      {box.receipt && <ContainmentReceipt r={box.receipt} />}

      {box.bugs.length > 0 && (
        <ul className="bugs">
          {box.bugs.map((b, i) => (
            <li key={b.id} className={`sev-${b.severity}`}>
              <span className="bug-n">{i + 1}</span>
              <span className="bug-sev">{b.severity}</span> {b.title}
            </li>
          ))}
        </ul>
      )}

      <ol className="steplog" ref={logRef}>
        {box.steps.length === 0 && <li className="muted">Waiting for first step...</li>}
        {box.steps.map((s, i) => (
          <li key={`${s.step}-${i}`} className={s.ok === false ? "bad" : undefined}>
            <span className="step-n">{s.step}</span>
            <span className="step-text">
              {s.log ?? s.thought ?? `${s.action ?? ""} ${s.selector ?? ""}`}
              {s.action && s.selector && <code>{s.action} {s.selector}</code>}
            </span>
          </li>
        ))}
      </ol>

      {box.summary && <p className="box-summary">{box.summary}</p>}

      <ScreenshotFilmstrip shots={box.screenshots} onOpen={onOpenShot} />
    </article>
  );
}
