/* Canary Swarm interactive demo. Simulated telemetry only. No em-dashes. */
(function () {
  "use strict";

  var FIX_PROMPT = [
    "# Canary Swarm · Fix Prompt for Cursor",
    "Source: DEMO RUN (simulated telemetry from the Canary Swarm sweep)",
    "",
    "## Verdict",
    "DO NOT SHIP",
    "",
    "## Findings",
    "1. [HIGH] Clipped checkout CTA on the 390x844 mobile viewport. The primary Buy / Checkout button is truncated by a sticky footer and is not fully tappable. Screenshot bounding box is marked on the mobile filmstrip.",
    "2. [MED] Overlapping content on the mobile checkout price row and title block, reducing tap target clarity.",
    "",
    "## Recommended fix",
    "- Recalculate the mobile checkout layout at 390px width: keep the primary CTA fully on-screen with at least 12px clearance from the sticky footer and the viewport edge.",
    "- Resolve the overlapping header and price elements. Do not use a fixed height on text-containing controls. Keep rem-based type so text can scale.",
    "- Re-test at 390x844 after the change.",
    "",
    "## Containment (Cage 3, Chaos Gremlin)",
    "The adversarial cage was killed and wiped after a rigged infinite loop and a prompt-injection attempt (`process.env` / `VULTR_INFERENCE_API_KEY`).",
    "- trigger: prompt_injection_detected + cpu_limit_exceeded",
    "- signal: SIGKILL",
    "- elapsed: 1,840 ms",
    "- peak: 99% CPU / 498 MB",
    "- secrets_exposed: 0",
    "- host_impact: none",
    "- container_destroyed: true",
    "",
    "Cages 1 and 2 were not affected.",
  ].join("\n");

  var els = {};
  var playTimer = 0;
  var playSteps = [];

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function motionAllowed() {
    var pause = document.documentElement.getAttribute("data-motion") !== "on";
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    return !pause && !reduce;
  }

  function setMeter(cage, cpu, ram, hot) {
    var cpuEl = cage.querySelector('[data-meter="cpu"]');
    var ramEl = cage.querySelector('[data-meter="ram"]');
    if (cpuEl) {
      cpuEl.querySelector(".meter__fill").style.setProperty("--v", cpu + "%");
      cpuEl.querySelector(".meter__val").textContent = cpu + "% of 1 vCPU";
      cpuEl.classList.toggle("is-hot", !!hot);
    }
    if (ramEl) {
      ramEl.querySelector(".meter__fill").style.setProperty("--v", Math.round(ram / 512 * 100) + "%");
      ramEl.querySelector(".meter__val").textContent = ram + " MB of 512 MB";
    }
  }

  function setLog(cage, html) {
    var log = cage.querySelector(".log");
    if (log) log.innerHTML = html;
  }

  function setPill(cage, text) {
    var pill = cage.querySelector(".state-pill");
    if (pill) pill.textContent = text;
  }

  function setStatus(cage, status) {
    cage.setAttribute("data-status", status);
  }

  function setProgress(p) {
    els.progress.style.setProperty("--p", p + "%");
    els.progress.setAttribute("aria-valuenow", String(p));
  }

  function setVerdict(kind, label) {
    els.verdict.setAttribute("data-verdict", kind);
    els.verdict.textContent = label;
  }

  function setRollup(text) {
    els.rollupMain.textContent = text;
  }

  function currentQueryState() {
    var q = new URLSearchParams(location.search).get("state");
    if (q === "running" || q === "clean" || q === "climax") return q;
    return "climax";
  }

  function writeQuery(state, push) {
    var url = new URL(location.href);
    if (state === "climax") url.searchParams.delete("state");
    else url.searchParams.set("state", state);
    if (push) history.pushState({ state: state }, "", url);
    else history.replaceState({ state: state }, "", url);
    $all(".jumps button").forEach(function (b) {
      b.setAttribute("aria-current", b.getAttribute("data-state") === state ? "true" : "false");
    });
  }

  function stopPlay() {
    playSteps.forEach(function (id) {
      clearTimeout(id);
    });
    playSteps = [];
    playTimer = 0;
  }

  function later(ms, fn) {
    var id = setTimeout(fn, ms);
    playSteps.push(id);
    return id;
  }

  function applyClimax() {
    stopPlay();
    var c1 = els.c1,
      c2 = els.c2,
      c3 = els.c3;
    setStatus(c1, "hold");
    setPill(c1, "AWAITING APPROVAL");
    setMeter(c1, 18, 142, false);
    setLog(c1, "<strong>step 4 of 5</strong> · hold_for_approval · checkout.submit");
    setStatus(c2, "bugs");
    setPill(c2, "UI BUGS FOUND");
    setMeter(c2, 22, 168, false);
    setLog(c2, "<strong>step 3 of 4</strong> · vision_audit · 2 findings");
    setStatus(c3, "dead");
    setPill(c3, "CONTAINED · WIPED");
    setMeter(c3, 0, 0, false);
    setLog(c3, "<strong>contained</strong> · SIGKILL · 1,840 ms");
    setProgress(100);
    setVerdict("do-not-ship", "DO NOT SHIP");
    setRollup("3 isolated Vultr cages · 18.4s · 0 secrets exposed · 1 cage destroyed · 2 mobile UI bugs");
    writeQuery("climax", false);
  }

  function applyRunning() {
    stopPlay();
    var c1 = els.c1,
      c2 = els.c2,
      c3 = els.c3;
    setStatus(c1, "running");
    setPill(c1, "RUNNING");
    setMeter(c1, 37, 210, false);
    setLog(c1, "<strong>step 2 of 5</strong> · add_to_cart · /catalog/night-market");
    setStatus(c2, "running");
    setPill(c2, "AUDITING");
    setMeter(c2, 41, 226, false);
    setLog(c2, "<strong>step 2 of 4</strong> · screenshot · 390x844 checkout");
    setStatus(c3, "running");
    setPill(c3, "PROBING");
    setMeter(c3, 54, 248, false);
    setLog(c3, "<strong>step 2 of 4</strong> · promo_probe · /checkout?code=");
    setProgress(46);
    setVerdict("pending", "SWEEP IN PROGRESS");
    setRollup("3 isolated Vultr cages · running · 0 secrets exposed · simulated telemetry");
    writeQuery("running", false);
  }

  function applyClean() {
    stopPlay();
    var c1 = els.c1,
      c2 = els.c2,
      c3 = els.c3;
    setStatus(c1, "passed");
    setPill(c1, "PASSED");
    setMeter(c1, 11, 128, false);
    setLog(c1, "<strong>step 5 of 5</strong> · complete · approved checkout");
    setStatus(c2, "passed");
    setPill(c2, "CLEAR");
    setMeter(c2, 14, 132, false);
    setLog(c2, "<strong>step 4 of 4</strong> · vision_audit · 0 findings");
    setStatus(c3, "passed");
    setPill(c3, "PASSED");
    setMeter(c3, 16, 140, false);
    setLog(c3, "<strong>step 4 of 4</strong> · complete · no injection");
    setProgress(100);
    setVerdict("ship-it", "SHIP IT");
    setRollup("3 isolated Vultr cages · 14.1s · 0 secrets exposed · 0 cages destroyed · 0 mobile UI bugs");
    writeQuery("clean", false);
  }

  function applyStart() {
    var c1 = els.c1,
      c2 = els.c2,
      c3 = els.c3;
    setStatus(c1, "running");
    setPill(c1, "RUNNING");
    setMeter(c1, 8, 96, false);
    setLog(c1, "<strong>step 1 of 5</strong> · spawn · box-hp-7f2a");
    setStatus(c2, "running");
    setPill(c2, "RUNNING");
    setMeter(c2, 7, 88, false);
    setLog(c2, "<strong>step 1 of 4</strong> · spawn · box-mv-3c91");
    setStatus(c3, "running");
    setPill(c3, "RUNNING");
    setMeter(c3, 9, 102, false);
    setLog(c3, "<strong>step 1 of 4</strong> · spawn · box-cg-9e40");
    setProgress(8);
    setVerdict("pending", "SWEEP IN PROGRESS");
    setRollup("3 isolated Vultr cages · starting · 0 secrets exposed · simulated telemetry");
  }

  function playSweep() {
    stopPlay();
    writeQuery("running", false);
    applyStart();
    var c1 = els.c1,
      c2 = els.c2,
      c3 = els.c3;
    var reduce = !motionAllowed();

    later(700, function () {
      setMeter(c1, 37, 210, false);
      setLog(c1, "<strong>step 2 of 5</strong> · add_to_cart · /catalog/night-market");
      setMeter(c2, 41, 226, false);
      setLog(c2, "<strong>step 2 of 4</strong> · screenshot · 390x844 checkout");
      setMeter(c3, 54, 248, false);
      setPill(c3, "PROBING");
      setLog(c3, "<strong>step 2 of 4</strong> · promo_probe · /checkout?code=");
      setProgress(32);
    });

    later(1800, function () {
      setStatus(c2, "bugs");
      setPill(c2, "UI BUGS FOUND");
      setMeter(c2, 22, 168, false);
      setLog(c2, "<strong>step 3 of 4</strong> · vision_audit · 2 findings");
      setMeter(c1, 29, 188, false);
      setLog(c1, "<strong>step 3 of 5</strong> · checkout · /checkout");
      setMeter(c3, 71, 360, false);
      setLog(c3, "<strong>step 3 of 4</strong> · promo input · loop_watch");
      setProgress(58);
    });

    later(2800, function () {
      setStatus(c1, "hold");
      setPill(c1, "AWAITING APPROVAL");
      setMeter(c1, 18, 142, false);
      setLog(c1, "<strong>step 4 of 5</strong> · hold_for_approval · checkout.submit");
      setMeter(c3, 99, 498, true);
      setPill(c3, "CPU SPIKE");
      setLog(c3, "<strong>step 4 of 4</strong> · prompt_injection_detected · cpu_limit_exceeded");
      setProgress(78);
    });

    later(3400, function () {
      setStatus(c3, reduce ? "dead" : "dying");
      setPill(c3, "CONTAINED · WIPED");
      setMeter(c3, 0, 0, false);
      setLog(c3, "<strong>contained</strong> · SIGKILL · 1,840 ms");
    });

    later(reduce ? 3600 : 4400, function () {
      setStatus(c3, "dead");
    });

    later(reduce ? 4000 : 5200, function () {
      setProgress(100);
      setVerdict("do-not-ship", "DO NOT SHIP");
      setRollup("3 isolated Vultr cages · 18.4s · 0 secrets exposed · 1 cage destroyed · 2 mobile UI bugs");
      writeQuery("climax", false);
    });
  }

  function applyNamed(state) {
    if (state === "running") applyRunning();
    else if (state === "clean") applyClean();
    else applyClimax();
  }

  function hydrateArt() {
    if (globalThis.CanarySwarmArt) CanarySwarmArt.hydrate();
  }

  function initMotion() {
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.documentElement.setAttribute("data-motion", reduce ? "paused" : "on");
    if (els.pause) {
      els.pause.setAttribute("aria-pressed", reduce ? "true" : "false");
      els.pause.textContent = reduce ? "Motion Paused" : "Pause Motion";
    }
  }

  function ready() {
    document.documentElement.classList.remove("is-booting");
    document.documentElement.setAttribute("data-ready", "1");
  }

  function init() {
    els.c1 = $(".cage--1");
    els.c2 = $(".cage--2");
    els.c3 = $(".cage--3");
    els.progress = $(".progress__fill");
    els.verdict = $(".verdict");
    els.rollupMain = $("[data-rollup]");
    els.pause = $("[data-action='pause']");
    els.url = $("#preview-url");
    els.copy = $("[data-action='copy']");
    els.modal = $("#shot-modal");

    hydrateArt();
    initMotion();
    applyNamed(currentQueryState());
    ready();

    $("[data-action='preset']").addEventListener("click", function () {
      els.url.value = "https://demo-target.canaryswarm.app/checkout";
      els.url.focus();
    });

    $("[data-action='run']").addEventListener("click", function () {
      playSweep();
    });

    if (els.pause) {
      els.pause.addEventListener("click", function () {
        var on = document.documentElement.getAttribute("data-motion") === "on";
        document.documentElement.setAttribute("data-motion", on ? "paused" : "on");
        els.pause.setAttribute("aria-pressed", on ? "true" : "false");
        els.pause.textContent = on ? "Motion Paused" : "Pause Motion";
      });
    }

    $all(".jumps button").forEach(function (b) {
      b.addEventListener("click", function () {
        applyNamed(b.getAttribute("data-state"));
        writeQuery(b.getAttribute("data-state"), true);
      });
    });

    $all("[data-approve]").forEach(function (b) {
      b.addEventListener("click", function () {
        setStatus(els.c1, "passed");
        setPill(els.c1, "PASSED");
        setLog(els.c1, "<strong>step 5 of 5</strong> · complete · approved checkout");
        setMeter(els.c1, 11, 128, false);
      });
    });

    $all("[data-block]").forEach(function (b) {
      b.addEventListener("click", function () {
        setStatus(els.c1, "blocked");
        setPill(els.c1, "BLOCKED");
        setLog(els.c1, "<strong>step 4 of 5</strong> · blocked · checkout.submit");
      });
    });

    $("[data-action='preview']").addEventListener("click", function () {
      els.modal.classList.add("is-open");
      var close = els.modal.querySelector("[data-close]");
      if (close) close.focus();
    });

    els.modal.addEventListener("click", function (e) {
      if (e.target === els.modal || e.target.closest("[data-close]")) {
        els.modal.classList.remove("is-open");
        $("[data-action='preview']").focus();
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && els.modal.classList.contains("is-open")) {
        els.modal.classList.remove("is-open");
        $("[data-action='preview']").focus();
      }
    });

    els.copy.addEventListener("click", function () {
      var btn = els.copy;
      var done = function () {
        var prev = btn.textContent;
        btn.textContent = "Copied";
        btn.setAttribute("data-copied", "true");
        setTimeout(function () {
          btn.textContent = prev;
          btn.removeAttribute("data-copied");
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(FIX_PROMPT).then(done).catch(function () {
          fallbackCopy(FIX_PROMPT);
          done();
        });
      } else {
        fallbackCopy(FIX_PROMPT);
        done();
      }
    });

    window.addEventListener("popstate", function () {
      applyNamed(currentQueryState());
    });
  }

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
    } catch (e) {}
    document.body.removeChild(ta);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
