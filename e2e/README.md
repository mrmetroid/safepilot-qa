# e2e: the three front ends, mobile + desktop, Playwright + Vultr vision

Checks the vanilla dashboard (control plane `/`), the React dashboard (`frontend/`, Vite) and the demo-target shop
at 390x844 and 1280x800. Every screen gets two independent verdicts: DOM geometry (elements clipped past the
left/right edge, sideways page scroll) and the product's own Mobile Vision audit on Vultr Serverless Inference.
`report/summary.md` shows whether they agree; `report/*-annotated.png` draws vision boxes red and DOM boxes blue.

```bash
cp .env.local.example .env          # then put your real VULTR_INFERENCE_API_KEY in .env (gitignored)
scripts/dev.sh --react              # :8000 control plane, :5173 React, :8081 demo-target
uv run --project e2e playwright install chromium
uv run --project e2e pytest         # add -m "not live" to skip real sweeps, --browser-channel chrome for Google Chrome
```

The demo-target home page is the instrument control: at 390px both checks must flag the clipped hero CTA; at
1280px neither may report a critical bug. If a control fails, fix the checker before trusting other results.
Without a key, vision checks and live sweeps are skipped (a `FAKE...` key counts as not set).
