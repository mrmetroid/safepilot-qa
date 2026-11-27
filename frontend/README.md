# Canary Swarm dashboard

Vite + React + TypeScript. Talks to the control plane only through the Section 6 contract in `../BUILD_SPEC.md`:
`GET /api/health`, `POST /api/runs`, `WS /ws/runs/{run_id}`, `GET /api/runs/{run_id}`, `POST /api/runs/{run_id}/boxes/{box_id}/approve`.

```bash
npm install
npm run dev     # http://localhost:5173, proxies /api and /ws to CONTROL_PLANE_URL (default http://127.0.0.1:8000)
npm run build   # outputs dist/, which Caddy serves on the Vultr VM (see BUILD_SPEC.md 8.2)
```

## Mock replay (UI rehearsal only)

Open `http://localhost:5173/?mock=1` to replay a scripted adversarial run with no backend: the approval bar, Containment Receipt, red boxes, verdict and copy button all work. It runs no browser, container or model. Never demo or record in mock mode.

## Additive events the UI understands (not in Section 6, optional)

- `vision_audit` `{box_id, step, summary, bugs[]}`: Box 2 results from the Mobile Vision Auditor (Section 4.6 shape). Bugs are also read from `boxes.box2.bugs` in the GET snapshot.
- `box_stats` `{box_id, cpu_pct, mem_mb}`: meter updates between steps.
- `screenshot` may carry `url` instead of `data_base64` (side channel per 6.3).
