import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In production Caddy serves dist/ and proxies /api and /ws on the same host.
// In dev, Vite proxies them to the local control plane.
const CONTROL_PLANE = process.env.CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": CONTROL_PLANE,
      "/ws": { target: CONTROL_PLANE, ws: true },
    },
  },
});
