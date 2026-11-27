import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { ApprovalBar } from "./components/ApprovalBar";
import { AnnotatedShot, hasBox } from "./components/AnnotatedShot";
import { BoxCard } from "./components/BoxCard";
import { UrlBar } from "./components/UrlBar";
import { VerdictBanner } from "./components/VerdictBanner";
import { createRun, decide, getHealth, getRun } from "./lib/api";
import { startMockRun, type MockHandle } from "./lib/mock";
import { newRun, reducer } from "./lib/state";
import { openRunSocket } from "./lib/ws";
import { BOX_IDS, type BoxId, type HealthResponse, type Shot } from "./lib/types";

// Mock replay is a dev-only rehearsal tool. It is compiled out of production builds.
const MOCK = import.meta.env.DEV && new URLSearchParams(location.search).has("mock");

function setRunParam(runId: string | null) {
  const u = new URL(location.href);
  if (runId) u.searchParams.set("run", runId);
  else u.searchParams.delete("run");
  history.replaceState(null, "", u);
}

function HealthDots({ health, error }: { health: HealthResponse | null; error: string | null }) {
  if (MOCK) return <div className="health"><span className="dot dot-warn" /> Mock replay (no backend)</div>;
  const item = (label: string, v?: string) => (
    <span className="health-item" key={label}>
      <span className={`dot ${v === "ok" ? "dot-ok" : v ? "dot-bad" : "dot-warn"}`} />
      {label}
    </span>
  );
  if (error && !health) return <div className="health">{item("Control plane unreachable", "down")}</div>;
  return (
    <div className="health" title={health?.inference_model ? `Model: ${health.inference_model}` : undefined}>
      {item("Control plane", health?.control_plane)}
      {item("Docker", health?.docker)}
      {item("Vultr Inference", health?.inference)}
    </div>
  );
}

export default function App() {
  const [run, dispatch] = useReducer(reducer, null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);
  const [startErr, setStartErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [pendingDecision, setPendingDecision] = useState<BoxId | null>(null);
  const [lightbox, setLightbox] = useState<Shot | null>(null);
  const closeSocket = useRef<(() => void) | null>(null);
  const mockRef = useRef<MockHandle | null>(null);
  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    if (MOCK) return;
    const poll = () =>
      getHealth()
        .then((h) => {
          setHealth(h);
          setHealthErr(null);
        })
        .catch((e) => setHealthErr(String(e.message ?? e)));
    poll();
    const t = window.setInterval(poll, 15000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => () => {
    closeSocket.current?.();
    mockRef.current?.stop();
  }, []);

  /** Open the run socket. Hydrates from GET /api/runs/{id} on every (re)connect and at key moments,
   * because Box 2 bugs and late state may only be present in the snapshot (Section 6.5). */
  const attach = useCallback((runId: string, wsUrl?: string) => {
    const hydrate = () =>
      getRun(runId)
        .then((snapshot) => dispatch({ kind: "snapshot", snapshot }))
        .catch(() => undefined);
    closeSocket.current = openRunSocket(wsUrl || `/ws/runs/${runId}`, {
      onEvent: (event) => {
        dispatch({ kind: "event", event });
        if (event.type === "run_verdict" || (event.type === "box_finished" && event.box_id === "box2")) hydrate();
      },
      onStatus: (connection) => dispatch({ kind: "connection", connection }),
      onOpen: hydrate,
      shouldReconnect: () => runRef.current?.status === "running",
    });
  }, []);

  // Late joiners and reloads: ?run=<id> rehydrates and reconnects, so a refresh never strands the approval gate.
  useEffect(() => {
    const runId = new URLSearchParams(location.search).get("run");
    if (MOCK || !runId) return;
    getRun(runId)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .then((snap: any) => {
        dispatch({ kind: "reset", run: newRun(runId, snap.mode ?? "custom", snap.url ?? "") });
        dispatch({ kind: "snapshot", snapshot: snap });
        if ((snap.status ?? "running") === "running") attach(runId);
        else dispatch({ kind: "connection", connection: "closed" });
      })
      .catch(() => setRunParam(null));
  }, [attach]);

  const start = useCallback(async (body: { mode: "adversarial_preset" } | { mode: "custom"; url: string }) => {
    closeSocket.current?.();
    mockRef.current?.stop();
    setStartErr(null);
    setStarting(true);
    try {
      if (MOCK) {
        const id = `mock-${Date.now()}`;
        dispatch({ kind: "reset", run: newRun(id, body.mode, body.mode === "custom" ? body.url : "/demo-target/", true) });
        dispatch({ kind: "connection", connection: "live" });
        mockRef.current = startMockRun(id, (event) => dispatch({ kind: "event", event }));
        return;
      }
      closeSocket.current = null;
      const res = await createRun(body);
      dispatch({ kind: "reset", run: newRun(res.run_id, res.mode, res.url) });
      setRunParam(res.run_id);
      attach(res.run_id, res.ws_url);
    } catch (e) {
      setStartErr(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }, [attach]);

  const onDecide = async (boxId: BoxId, d: "approve" | "block") => {
    if (!run) return;
    setPendingDecision(boxId);
    try {
      if (run.mock) mockRef.current?.decide(boxId, d);
      else await decide(run.run_id, boxId, d);
      dispatch({ kind: "decision", box_id: boxId, decision: d });
    } catch (e) {
      setStartErr(`Decision not accepted: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPendingDecision(null);
    }
  };

  // A run with a dead socket must not lock the operator out of starting a new one.
  const running = run?.status === "running" && run.connection !== "closed";
  const box2 = run?.boxes.box2;
  const annotatedBox = run ? run.boxes[run.annotated_box_id ?? "box2"] : undefined;
  const annotatedStep = run?.annotated_step ?? annotatedBox?.vision_step ?? null;
  const annotatedShot =
    annotatedBox?.screenshots.find((s) => s.step === annotatedStep) ?? annotatedBox?.screenshots.at(-1) ?? null;
  const bugs = (annotatedBox?.bugs?.length ? annotatedBox.bugs : box2?.bugs ?? []).filter(hasBox);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden>
            <path d="M16 3l11 5v8c0 7-5 12-11 13C10 28 5 23 5 16V8z" fill="var(--green)" />
            <path d="M11 16l4 4 7-8" stroke="var(--bg)" strokeWidth="3" fill="none" />
          </svg>
          <div>
            <h1>Canary Swarm</h1>
            <p>Untrusted AI code deserves untrusted AI testers in disposable boxes.</p>
          </div>
        </div>
        <HealthDots health={health} error={healthErr} />
      </header>

      <UrlBar busy={starting || running} onPreset={() => start({ mode: "adversarial_preset" })} onCustom={(url) => start({ mode: "custom", url })} />
      {startErr && <div className="error-banner">{startErr}</div>}

      {run && (
        <div className="runmeta">
          <span>
            Run <code>{run.run_id.slice(0, 8)}</code> · {run.mode === "adversarial_preset" ? "Adversarial preset" : "Custom URL"} ·{" "}
            <a href={run.url} target="_blank" rel="noreferrer">{run.url}</a>
          </span>
          <span className={`conn conn-${run.connection}`}>{run.mock ? "mock" : run.connection}</span>
        </div>
      )}

      {run &&
        BOX_IDS.map((id) => {
          const b = run.boxes[id];
          return b.approval && b.status === "waiting_for_approval" ? (
            <ApprovalBar key={id} boxId={id} boxName={`Box ${BOX_IDS.indexOf(id) + 1} ${b.name}`} request={b.approval} pending={pendingDecision === id} onDecide={(d) => onDecide(id, d)} />
          ) : null;
        })}

      {run?.verdict && <VerdictBanner verdict={run.verdict} headline={run.headline} fixPrompt={run.fix_prompt} />}

      {run ? (
        <main className="grid">
          {BOX_IDS.map((id, i) => (
            <BoxCard key={id} box={run.boxes[id]} index={i} onOpenShot={setLightbox} />
          ))}
        </main>
      ) : (
        <section className="empty">
          <h2>Three disposable browsers. One verdict.</h2>
          <ol>
            <li><strong>Box 1 Happy Path</strong> walks to checkout and waits for your Approve or Block.</li>
            <li><strong>Box 2 Mobile Vision Check</strong> audits a 390x844 screenshot and boxes the bugs in red.</li>
            <li><strong>Box 3 Chaos Gremlin</strong> pokes hostile paths. If it trips a loop or injection, it is killed and wiped with a Containment Receipt.</li>
          </ol>
        </section>
      )}

      {run && annotatedShot && bugs.length > 0 && (
        <section className="report">
          <div className="report-shot">
            <h3>Red-boxed screenshot</h3>
            <AnnotatedShot shot={annotatedShot} bugs={bugs} />
          </div>
          <div className="report-side">
            <h3>Findings</h3>
            {box2?.vision_summary && <p>{box2.vision_summary}</p>}
            <ol className="findings">
              {bugs.map((b) => (
                <li key={b.id} className={`sev-${b.severity}`}>
                  <strong>{b.title}</strong> <span className="bug-sev">{b.severity}</span>
                  <p>{b.description}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>
      )}

      {run?.fix_prompt && (
        <section className="report-fix">
          <h3>Fix prompt for Cursor</h3>
          <textarea className="fixprompt" readOnly value={run.fix_prompt} onFocus={(e) => e.currentTarget.select()} />
        </section>
      )}

      {lightbox && (
        <div className="lightbox" onClick={() => setLightbox(null)} role="dialog">
          <img src={lightbox.src} alt={`Step ${lightbox.step}`} />
        </div>
      )}

      <footer className="foot">Hosted on Vultr Cloud Compute, Stockholm. Planning and vision by Vultr Serverless Inference.</footer>
    </div>
  );
}
