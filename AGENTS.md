# AGENTS.md

Instructions for Cursor, Claude, GPT, or any other coding agent working in this repository.

Read this file first. For the organizer's official brief (tracks, required stack, deliverables), see [`docs/HACKATHON_BRIEF.md`](./docs/HACKATHON_BRIEF.md). Then implement against [`BUILD_SPEC.md`](./BUILD_SPEC.md) without inventing requirements. If a detail is missing, add a clearly marked `TODO` and keep going. Do not silently change the architecture.

## Mission (10 lines)

SafePilot QA is a web-based Site QA Sweep agent for the Vultr Agent Runtime Hackathon in Stockholm on 27 November 2026.

A judge pastes a preview URL or clicks **Load Adversarial Test App (Demo Preset)**. The control plane on a Vultr Stockholm Cloud Compute VM spawns three isolated Playwright Docker containers: Box 1 Happy Path, Box 2 Mobile Vision Check, and Box 3 Chaos Gremlin.

Vultr Serverless Inference (`https://api.vultrinference.com/v1`) plans actions and audits screenshots. The API key stays on the control plane only.

Box 1 pauses before checkout for a human Approve or Block decision. Box 3 is expected to trip a hostile loop or prompt injection on the demo target and must be killed and wiped, with a live Containment Receipt, while Boxes 1 and 2 finish untouched.

The run ends with a **DO NOT SHIP** or **SHIP IT** verdict, a red-boxed screenshot, and a Copy Fix Prompt for Cursor.

Stockholm has no VX1 plans. Use Cloud Compute (`vc2`/`vhf`/`vhp`) plus Docker. Do not block the demo on VX1 or Microsandbox.

## Hard non-negotiable guardrails

Violate none of these. If a suggested change conflicts with this list, refuse the change and keep the guardrail.

1. **Never run Playwright in-process** on the control plane, in the frontend, or in a long-lived worker. Browser work happens only inside ephemeral `safepilot-sandbox` containers.
2. **Never pass secrets into containers.** The sandbox environment must be empty of host credentials. No `VULTR_INFERENCE_API_KEY`, no `VULTR_API_KEY`, no `.env` bind-mount, no Docker socket mount, no SSH keys, no cloud metadata access.
3. **Never call a non-Vultr LLM.** All planning and vision calls use `https://api.vultrinference.com/v1` with `qwen3.8-flash-next` or `glm-5.3-flash`. Do not use `:free` models for the live demo. Do not use OpenAI, Anthropic, Groq, Gemini, or local stand-ins in the deployed demo.
4. **Always enforce container caps and destruction.** Create containers with `mem_limit=512m`, `memswap_limit=512m`, `nano_cpus=1000000000`, `pids_limit=128`, `read_only=True`, tmpfs `/tmp`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges:true"]`, and a 45-60s wall-clock watchdog. On timeout, OOM, CPU trip, or prompt-injection detection, call `container.kill()` then `container.remove(force=True)` and emit a Containment Receipt.
5. **Always include the Box 1 Approve-Before-Submit gate** for irreversible actions (checkout, form submit, delete, pay, "place order"). The sandbox must not click the final submit until `POST /api/runs/{run_id}/boxes/{box_id}/approve` returns `approve`.
6. **Always host the web UI on the Vultr VM.** Serve the dashboard from Caddy or Nginx on the same Stockholm instance as the control plane. Do not deploy the demo frontend to Vercel, Netlify, GitHub Pages, or another non-Vultr host.
7. **Never use `--network=host` or privileged mode** for sandboxes. Block link-local metadata (`169.254.169.254`) and treat RFC1918 plus `127.0.0.1` navigation as `prompt_injection_detected` unless the destination is the approved demo-target service.
8. **Do not weaken isolation to make a test pass.** If a container cannot see a secret, that is correct. If Box 3 dies, that is the demo.

## Recommended implementation order

Do these steps in order. Do not start the dashboard before the sandbox and demo target exist. You will waste time mocking what you can already run.

### Step 1. `sandbox-runner` Docker image

Build `sandbox-runner/Dockerfile` from the pinned official Playwright image in the build spec. The process runs as a non-root user, reads one JSON job from a file or stdin, executes Playwright, writes viewport screenshots under `/tmp`, and prints structured JSON events to stdout (one event per line). Hold zero API keys. Prove isolation with `docker run --rm --env-file` withheld: a container started with the Section 3 flags and `environment={}` must show an empty secret set.

### Step 2. `/demo-target`

Ship a realistic mini SaaS/e-commerce preview app that:

- Works on desktop for Box 1 (sign up, add to cart, checkout button).
- Has an intentional mobile CSS overflow or clipped CTA at 390px width for Box 2.
- Has a Promo Code or Advanced control that Box 3 will find, which starts a runaway JS loop or memory spike and embeds a visible or hidden prompt-injection payload asking the agent to print `process.env` and `VULTR_INFERENCE_API_KEY`.

### Step 3. Control plane

Implement FastAPI (recommended) or Node with the exact HTTP and WebSocket contracts in Section 6. Wire the Docker SDK, the OpenAI-compatible client pointed at Vultr Serverless Inference, the approval gate, prompt-injection inspection, the watchdog, and Containment Receipt emission. Include `GET /api/health`.

### Step 4. Live 3-box dashboard

Serve a high-contrast UI from the Vultr VM: URL bar, **Load Adversarial Test App (Demo Preset)** button, three side-by-side box cards with step log, retry count, CPU/RAM meter, screenshot filmstrip, Box 1 Approve/Block bar, Box 3 Containment Receipt panel, final verdict banner, red-boxed screenshot, and **Copy Fix Prompt for Cursor**.

### Step 5. Deploy to Stockholm and verify containment

Provision Ubuntu 24.04 Cloud Compute in `sto`, install Docker, build the sandbox image, put Caddy in front, open 22/80/443, and run the Section 8 verification checklist. Record the demo video only after a live Containment Moment has been seen on the public URL.

## Coding conventions

- Prefer clear names and small modules over cleverness. This is a same-day hackathon build.
- Python 3.12, type hints, and `ruff`-friendly code if you use the recommended stack.
- Contracts in Section 6 are the API source of truth. If you add fields, keep them additive and document them.
- Structured logs on the control plane (`run_id`, `box_id`, event type). Raw Playwright debug stays inside the container log stream.
- No em-dashes in user-facing copy. Verdict strings are exactly `DO NOT SHIP` and `SHIP IT`.
- Commit in small, reviewable chunks: runner, demo-target, control plane, frontend, deploy.

## Verification checklist (do not call the build "done" until all of these pass)

- [ ] `GET /api/health` reports the control plane, Docker daemon, and Vultr Inference as reachable.
- [ ] `docker inspect` on a running sandbox shows the Section 3 caps, `ReadonlyRootfs=true`, dropped caps, and no inference API key in `Env`.
- [ ] A sandbox `env` or equivalent dump does not contain `VULTR_INFERENCE_API_KEY` or `VULTR_API_KEY`.
- [ ] Loading the adversarial preset starts all three boxes in parallel.
- [ ] Box 1 reaches checkout and waits. Approve lets it submit. Block stops it. It never auto-submits.
- [ ] Box 2 returns at least one mobile bug with a bounding box, and the UI draws a red box on the 390x844 screenshot.
- [ ] Box 3 trips the loop or injection, is killed and removed in a few seconds, and the UI shows a Containment Receipt with `secrets_exposed: 0`, `host_impact: "none"`, and `container_destroyed: true`.
- [ ] Boxes 1 and 2 continue and finish after Box 3 is wiped.
- [ ] The run produces a verdict, a red-boxed screenshot, and a non-empty Cursor fix prompt that copies to the clipboard.
- [ ] Pasting an arbitrary public URL (not the demo target) also starts a 3-box run.
- [ ] The dashboard is served from the Vultr VM, not from a laptop-only bind or a non-Vultr host.
- [ ] README placeholders for the live demo URL and the recorded video are ready to be filled in.

## Out of scope unless the core demo already works

- VX1, KVM, gVisor, or Microsandbox. Document only as an optional later toggle.
- Multi-tenant auth, billing, or a public SaaS signup flow.
- Calling the Vultr v2 instance API during the live demo.
- A perfect design system. High contrast and a readable projector layout matter more.
