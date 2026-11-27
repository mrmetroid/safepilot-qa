# Canary Swarm demo prototype

Static HTML, CSS, and JS. No build step. Serve this folder (Caddy, Nginx, or `python3 -m http.server`) or lift the tokens, cage markup, canary SVG, and state machine into the Vite/React dashboard.

## Demo states

- Default, and `?state=climax`: money shot. Cage 1 awaiting approval, Cage 2 red-boxed mobile bugs, Cage 3 dead canary and Containment Receipt, `DO NOT SHIP`.
- `?state=running`: mid-sweep, all three birds hopping.
- `?state=clean`: all cages passed, `SHIP IT` (simulated clean run).
- `Run Sweep` plays the accelerated sequence from spawn to the climax.

Motion opts in with `prefers-reduced-motion: no-preference`. Use Pause Motion in the top bar. Telemetry is simulated and labeled as a Demo Run.

Locked copy strings from the build spec are used as specified: Load Adversarial Test App (Demo Preset), Approve, Block, Containment Receipt, DO NOT SHIP, SHIP IT, Copy Fix Prompt for Cursor.
