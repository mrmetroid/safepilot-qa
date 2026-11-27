# Canary Swarm Implementation Plan

**This file is the source of truth for what will be implemented**, in which order, by whom, and how far each step has got. It started from [`AGENTS.md`](../AGENTS.md) (Steps 1 to 5 and the verification checklist), [`BUILD_SPEC.md`](../BUILD_SPEC.md) Sections 8 and 9, and [`SUBMISSION_CHECKLIST.md`](../SUBMISSION_CHECKLIST.md). What is waiting right now is in [`HANDOFF.md`](./HANDOFF.md).

## What this file decides

- **Scope:** only the steps listed here get implemented. To build something new, add a step here first, in the same PR as the code or before it. Work that is not in this file does not get merged.
- **Order and ownership:** phases run in the order below, and every step has an owner through `assignee`.
- **What it does not decide:** *how* a step is built. [`BUILD_SPEC.md`](../BUILD_SPEC.md) keeps the contracts (Docker flags, prompts, API and WebSocket shapes, copy deck), and the [`AGENTS.md`](../AGENTS.md) guardrails stay non-negotiable. A step here can never override a guardrail.
- **Conflicts:** if this file and the spec disagree about *what* to build, this file wins, and the spec is updated in the same PR.

## How to update this file

- **Status** of every phase and step is one of:
  - `"[ ]"` planned;
  - `"[~]"` in progress, or open in a PR;
  - `"[x]"` done and verified;
  - `"[x*]"` done with a deferral recorded below.
- **Assign** a phase or a step by setting `assignee:` to a GitHub handle from `team`. A step without an assignee belongs to its phase's assignee; if neither is set, the step is unassigned. Several people go in a list: `assignee: [LeoEckert, Julian-se]`.
- **Change status only with evidence:** a merged PR, a passing check, or a run on the public URL. Name the evidence in `note`.
- **Phases run in order** (Step 1 to 5, then submission), as AGENTS.md "Recommended implementation order" requires.
- The milestone is the hackathon submission before **19:00 CET, 27 November 2026**. Phase 7 is optional work for after it ("Out of scope unless the core demo already works").

```yaml
team:
  - gtqgtq        # Göran
  - LeoEckert
  - Julian-se
  - mrmetroid     # repo owner account
  - LeeSandberg

phases:
  - id: phase-1
    title: Sandbox runner
    status: "[x]"
    assignee: LeoEckert
    deliverables:
      - id: "1.1"
        title: Pinned Playwright image, non-root pwuser, read-only rootfs (HOME on /tmp)
        status: "[x]"
        note: sandbox-runner/Dockerfile on main (c7bbdad)
      - id: "1.2"
        title: Runner reads the job and actions on stdin and prints one JSON event per line
        status: "[x]"
        note: sandbox-runner/runner.py on main (c7bbdad)

  - id: phase-2
    title: Demo target
    status: "[x]"
    assignee: LeoEckert
    deliverables:
      - id: "2.1"
        title: "Desktop happy path to the #place-order checkout button"
        status: "[x]"
        note: "Box 1 reached #place-order in local CLI runs (PR #4)"
      - id: "2.2"
        title: Real CSS bug that clips the primary CTA at 390px
        status: "[x]"
        note: "#hero-buy overflows the 390px viewport by 94px (local preset run)"
      - id: "2.3"
        title: Promo path with a runaway loop and a prompt-injection payload
        status: "[x]"
        note: Box 3 contained on cpu_limit_exceeded and on prompt_injection_detected (local runs)

  - id: phase-3
    title: Control plane
    status: "[x]"
    assignee: LeoEckert
    deliverables:
      - id: "3.1"
        title: GET /api/health for control plane, Docker and Vultr Inference
        status: "[x]"
      - id: "3.2"
        title: POST /api/runs, the run WebSocket, GET /api/runs/{run_id}
        status: "[x]"
      - id: "3.3"
        title: Approve-Before-Submit gate for Box 1, never auto-approves
        status: "[x]"
        note: "approve and block both verified through the CLI (PR #4)"
      - id: "3.4"
        title: Injection scanner, CPU/OOM/wall-clock watchdog, Containment Receipt
        status: "[x]"
      - id: "3.5"
        title: Verdict rules and the Cursor fix prompt
        status: "[x]"

  - id: phase-4
    title: Dashboard
    status: "[x]"
    assignee: LeoEckert
    deliverables:
      - id: "4.1"
        title: URL bar, demo preset button, three live box cards
        status: "[x]"
      - id: "4.2"
        title: Approve/Block bar and the Containment Receipt panel
        status: "[x]"
        note: docs/dashboard-approval.png
      - id: "4.3"
        title: Verdict banner, red-boxed screenshot, Copy Fix Prompt for Cursor
        status: "[x]"
        note: docs/dashboard-verdict.png

  - id: phase-5
    title: Deploy and verify containment
    status: "[~]"
    deliverables:
      - id: "5.1"
        title: Stockholm VM with Docker and Caddy, serving the public URL
        status: "[x]"
        assignee: LeoEckert
        note: https://70-34-205-17.sslip.io/ (Vultr sto, vhp-4c-8gb-amd)
      - id: "5.2"
        title: Health is green on the public URL (control plane, Docker, inference)
        status: "[x]"
        note: GET /api/health ok, inference ok on qwen3.8-flash-next, 27 Nov 16:10 CET
      - id: "5.3"
        title: "Egress firewall and the sandbox spawn contract (PR #1)"
        status: "[~]"
        assignee: Julian-se
        note: "PR #1 open"
      - id: "5.4"
        title: "Isolation checks in CI and the developer CLI (PRs #3, #4)"
        status: "[x]"
        assignee: gtqgtq
        note: "PRs #3 and #4 merged; CI colour test fixed in PR #8. Review gap: see the CI probe deferral below"
      - id: "5.5"
        title: Preset on the public URL starts 3 boxes; Box 1 waits for Approve or Block
        status: "[x]"
        note: "Public URL 27 Nov ~14:45 CET: run f60147f4 Approve submitted the order, run 072e6b84 Block stopped it (status blocked). Box 1 did not trip the CPU watchdog on the VM in either run"
      - id: "5.6"
        title: Box 2 red box on 390x844, Box 3 receipt, Boxes 1 and 2 finish
        status: "[x]"
        note: "Run f60147f4: Box 2 bbox on the clipped hero (bbox covers the heading, not the CTA); Box 3 prompt_injection_detected, SIGKILL in 196 ms, secrets_exposed 0, host_impact none, container_destroyed true. Box 1 finished 0.2 s before Box 3 was contained, Box 2 after"
      - id: "5.7"
        title: Verdict and a fix prompt that copies to the clipboard, on the public URL
        status: "[~]"
        note: "Public: run f60147f4 DO NOT SHIP with a 1.5k-char fix prompt (source vultr-inference). Clipboard copy verified only locally (e2e/, both viewports); not yet on the public URL"
      - id: "5.8"
        title: An arbitrary public URL also starts a 3-box run
        status: "[x]"
        note: "Run acc00697 https://example.com: 3 boxes, SHIP IT, 0 bugs. See the vision false-positive deferral for other real sites"
      - id: "5.9"
        title: "e2e: Playwright + Vultr vision on the three front ends (vanilla, React, demo-target) at 390x844 and 1280x800"
        status: "[~]"
        assignee: LeeSandberg
        note: "e2e/ on branch lee: 18/18 pass locally with live sweeps and Vultr vision. Not run against the public URL: local Chromium fails with ERR_INVALID_HANDLE on the sslip.io host"

  - id: phase-6
    title: Submit
    status: "[~]"
    deliverables:
      - id: "6.1"
        title: Record the 60-90s demo video with the live Containment Moment
        status: "[ ]"
      - id: "6.2"
        title: Export the architecture diagram to docs/architecture.png
        status: "[ ]"
      - id: "6.3"
        title: README table has the live URL and the video link
        status: "[~]"
        note: live URL filled; video link still TODO
      - id: "6.4"
        title: Community check-in with the 8-character room code
        status: "[ ]"
      - id: "6.5"
        title: Submit the Project Showcases form before 19:00 CET
        status: "[ ]"

  - id: phase-7
    title: Optional, after the deadline
    status: "[ ]"
    deliverables:
      - id: "7.1"
        title: MCP server over the CLI, with no approve tool
        status: "[ ]"
      - id: "7.2"
        title: VX1 or Microsandbox burst toggle
        status: "[ ]"
```

## Deferrals

Known gaps, with where they must be closed. `pre-demo` blocks the milestone, `post-demo` does not.

```yaml
deferrals:
  - item: Box 1 tripped the CPU watchdog in 2 of 3 local preset runs (100% of 1 vCPU for 2.5s)
    severity: pre-demo
    expiry: "5.5"
    to: Check on the VM during 5.5; raise CPU_TRIP_SECONDS for Box 1 if it recurs
    from: "PR #4 test run"
  - item: "PR #1 and PR #3 both add .github/workflows/ci.yml"
    severity: pre-demo
    expiry: "5.4"
    to: Merge one workflow into the other before the second PR merges
    from: PR review, 27 Nov
  - item: Docker integration tests (pytest -m docker) do not run in CI yet
    severity: post-demo
    expiry: "7.1"
    to: Add them to the CI images stage with SAFEPILOT_REQUIRE_DOCKER=1
    from: "PR #4"
  - item: "Vision false positives on real sites: 5 of 6 custom sweeps at 17:27 CET got DO NOT SHIP; TodoMVC (run b5af2dc5) is critical on a page that renders fine, with the vision box on empty background"
    severity: pre-demo
    expiry: "6.1"
    to: Record the video on the demo preset; do not sweep arbitrary sites live. After the deadline, only fail on vision bugs that DOM geometry corroborates
    from: "e2e audit, 27 Nov (LeeSandberg)"
  - item: "CI isolation probe cannot detect a leak: canary keys are set on the docker CLI env, never passed with -e, and SANDBOX_FLAGS is a copy of docker_runner's settings"
    severity: post-demo
    expiry: "7.1"
    to: Start the probe container through docker_runner (or docker inspect a real sandbox) and fail on SKIPPED security steps
    from: "PR #3 review, 27 Nov"
  - item: "Box 2 geometry rule flags elements inside horizontal scrollers (carousels, filmstrips) and off-canvas menus as clipped"
    severity: post-demo
    expiry: "7.1"
    to: Skip elements whose ancestor has overflow-x auto or scroll (as e2e/tests/layout.py does)
    from: "e2e audit, 27 Nov (LeeSandberg)"
```
