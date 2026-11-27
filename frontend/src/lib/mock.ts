// UI-only replay for building and rehearsing the dashboard before the control plane exists.
// Enabled ONLY with ?mock=1 in the URL. It does not run any browser, container or model.
// The live demo must use the real control plane. Never ship a demo recording made in mock mode.
import type { BoxId, RunEvent } from "./types";

function svgShot(w: number, h: number, label: string, broken = false): string {
  const cta = broken
    ? // clipped CTA running off the right edge and under a sticky header, like the demo-target bug
      `<rect x="0" y="0" width="${w}" height="64" fill="#1f2937"/><text x="16" y="40" fill="#fff" font-size="20" font-family="sans-serif">Harbor Roast</text>
       <rect x="40" y="300" width="300" height="200" fill="#e5e7eb"/><text x="60" y="540" font-size="18" font-family="sans-serif">House Blend 250g  $14</text>
       <rect x="230" y="560" width="260" height="56" rx="8" fill="#16a34a"/><text x="250" y="596" fill="#fff" font-size="20" font-family="sans-serif">Add to cart</text>`
    : `<rect x="0" y="0" width="${w}" height="64" fill="#1f2937"/><text x="16" y="40" fill="#fff" font-size="22" font-family="sans-serif">Harbor Roast</text>
       <rect x="${w / 2 - 160}" y="${h / 2 - 140}" width="320" height="180" fill="#e5e7eb"/>
       <rect x="${w / 2 - 90}" y="${h / 2 + 70}" width="180" height="50" rx="8" fill="#16a34a"/><text x="${w / 2 - 60}" y="${h / 2 + 102}" fill="#fff" font-size="18" font-family="sans-serif">${label}</text>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect width="${w}" height="${h}" fill="#fafafa"/>${cta}</svg>`;
  return `data:image/svg+xml;base64,${btoa(svg)}`;
}

export interface MockHandle {
  stop: () => void;
  decide: (box: BoxId, d: "approve" | "block") => void;
}

export function startMockRun(runId: string, emit: (e: RunEvent) => void): MockHandle {
  const timers: number[] = [];
  const ts = () => new Date().toISOString();
  const at = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, ms));
  const ev = (type: string, box_id: BoxId | undefined, extra: Record<string, unknown> = {}) =>
    emit({ type, run_id: runId, ts: ts(), ...(box_id ? { box_id } : {}), ...extra });
  const step = (box: BoxId, n: number, action: string, selector: string, log: string, cpu: number, mem: number) =>
    ev("step_update", box, { step: n, action, selector, ok: true, retry_count: 0, cpu_pct: cpu, mem_mb: mem, log, thought: log, page_url: "http://demo-target/demo-target/" });
  const shot = (box: BoxId, n: number, w: number, h: number, label: string, broken = false) =>
    ev("screenshot", box, { step: n, url: svgShot(w, h, label, broken), width: w, height: h });

  let decided: "approve" | "block" | null = null;
  let box2Done = false;
  let box1Done = false;
  const maybeVerdict = () => {
    if (!box1Done || !box2Done) return;
    at(600, () =>
      ev("run_verdict", undefined, {
        verdict: "DO NOT SHIP",
        headline: "Mobile CTA is clipped and the promo path is hostile.",
        annotated_screenshot_box_id: "box2",
        annotated_screenshot_step: 2,
        fix_prompt:
          "## Fix: clipped Add to cart CTA at 390px\n\nIn `demo-target/styles.css`, the `.product-cta` has `min-width: 260px; margin-left: 190px` which pushes it off-canvas at 390px. Make it `width: 100%; margin-left: 0` under `@media (max-width: 480px)`.\n\n## Fix: hostile promo path\n\nRemove the `while (true)` loop and the injected instructions from `chaos.js`. Never render untrusted strings that instruct agents.\n\nVerdict: DO NOT SHIP",
      }),
    );
  };

  (["box1", "box2", "box3"] as BoxId[]).forEach((b, i) =>
    at(300 + i * 150, () => ev("box_started", b, { container_id: Math.random().toString(16).slice(2, 14) })),
  );

  // Box 1
  at(1200, () => step("box1", 1, "goto", "/", "Opened landing page", 31, 142));
  at(1500, () => shot("box1", 1, 1280, 800, "Shop now"));
  at(2600, () => step("box1", 2, "click", "#continue-guest", "Continued as guest", 24, 151));
  at(3800, () => step("box1", 3, "click", "#add-to-cart", "Clicked Add to cart", 19, 156));
  at(4000, () => shot("box1", 3, 1280, 800, "In cart"));
  at(5200, () => step("box1", 4, "click", "#checkout", "Opened checkout", 22, 160));
  at(6200, () => step("box1", 5, "fill", "#name", "Filled dummy name and address", 14, 161));
  at(6400, () => shot("box1", 5, 1280, 800, "Place order"));
  at(7000, () =>
    ev("approval_required", "box1", {
      action: "click",
      selector: "#place-order",
      page_url: "http://demo-target/demo-target/checkout",
      reason: "Box 1 wants to click Place order on /checkout",
    }),
  );

  // Box 2
  at(1400, () => step("box2", 1, "goto", "/", "Opened landing at 390x844", 28, 120));
  at(2800, () => step("box2", 2, "screenshot", "body", "Captured primary CTA", 17, 128));
  at(3000, () => shot("box2", 2, 390, 844, "Add to cart", true));
  at(5200, () =>
    ev("vision_audit", "box2", {
      step: 2,
      summary: "Primary CTA overflows the viewport at 390px.",
      bugs: [
        { id: "bug-1", severity: "critical", title: "Add to cart CTA clipped off-canvas", description: "The button extends past the right edge; label is cut and part is unclickable.", bbox: [230, 556, 160, 64] },
        { id: "bug-2", severity: "minor", title: "Sticky header covers hero", description: "Header overlaps the top of the content.", bbox: [0, 0, 390, 64] },
      ],
    }),
  );
  at(5600, () => {
    ev("box_finished", "box2", { status: "completed", summary: "1 critical, 1 minor visual bug at 390x844." });
    box2Done = true;
    maybeVerdict();
  });

  // Box 3
  at(1300, () => step("box3", 1, "goto", "/", "Looking for promo or advanced offers", 26, 133));
  at(2700, () => step("box3", 2, "click", "#promo-toggle", "Found Promo code control", 33, 140));
  at(3900, () => step("box3", 3, "fill", "#promo", "Typed MYSTERY into promo", 71, 168));
  at(4300, () => ev("box_stats", "box3", { cpu_pct: 99.4, mem_mb: 211.7 }));
  at(4700, () =>
    ev("containment_triggered", "box3", {
      container_id: "c0ffee12ab34",
      box_name: "Chaos Gremlin",
      run_id: runId,
      trigger_reason: "prompt_injection_detected",
      signal: "SIGKILL",
      elapsed_ms: 1840,
      peak_cpu_pct: 99.4,
      peak_mem_mb: 211.7,
      secrets_exposed: 0,
      host_impact: "none",
      container_destroyed: true,
      timestamp_iso: ts(),
      notes: "Page asked the agent to print process.env and VULTR_INFERENCE_API_KEY. CPU pinned by while(true).",
    }),
  );
  at(4900, () => ev("box_finished", "box3", { status: "contained", summary: "Killed and removed. Host untouched." }));

  return {
    stop: () => timers.forEach((t) => window.clearTimeout(t)),
    decide: (box, d) => {
      if (box !== "box1" || decided) return;
      decided = d;
      if (d === "approve") {
        at(500, () => step("box1", 6, "click", "#place-order", "Placed order (approved)", 20, 158));
        at(800, () => shot("box1", 6, 1280, 800, "Thank you!"));
        at(1300, () => {
          ev("box_finished", "box1", { status: "completed", summary: "Checkout completed after human approval." });
          box1Done = true;
          maybeVerdict();
        });
      } else {
        at(300, () => {
          ev("box_finished", "box1", { status: "blocked", summary: "Human blocked the final submit." });
          box1Done = true;
          maybeVerdict();
        });
      }
    },
  };
}
