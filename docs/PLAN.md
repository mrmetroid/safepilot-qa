# SafePilot QA Implementation Plan

This is the implementation plan from [`AGENTS.md`](../AGENTS.md) (Steps 1 to 5 and the verification checklist), [`BUILD_SPEC.md`](../BUILD_SPEC.md) Sections 8 and 9, and [`SUBMISSION_CHECKLIST.md`](../SUBMISSION_CHECKLIST.md), as one tracked list. The spec stays the source of truth for *what* to build. This file tracks *status* and *who owns what*. What is waiting right now is in [`HANDOFF.md`](./HANDOFF.md).

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
        status: "[~]"
        assignee: gtqgtq
        note: "PR #3 (CI with the Section 8.4 probe) and PR #4 (safepilot sandbox verify) open"
      - id: "5.5"
        title: Preset on the public URL starts 3 boxes; Box 1 waits for Approve or Block
        status: "[ ]"
      - id: "5.6"
        title: Box 2 red box on 390x844, Box 3 receipt, Boxes 1 and 2 finish
        status: "[ ]"
      - id: "5.7"
        title: Verdict and a fix prompt that copies to the clipboard, on the public URL
        status: "[ ]"
      - id: "5.8"
        title: An arbitrary public URL also starts a 3-box run
        status: "[ ]"

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
```
