import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Dev-only proxy so `pnpm dev` (:5173) can talk to the agent server (:8765)
// without tripping its CORS allowlist (which only admits the Docker-served UI
// origin). Used together with `VITE_AGENT_BASE=` (empty) in `.env.local`,
// which makes api.ts issue relative requests. SSE streams proxy fine.
const AGENT_PATHS = [
  "/ping",
  "/presets",
  "/skills",
  "/mcp_servers",
  "/incidents",
  "/run",
  "/runs",
]

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      AGENT_PATHS.map((p) => [p, { target: "http://localhost:8765" }]),
    ),
  },
})
