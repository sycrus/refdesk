// Built to ui/dist and served by the FastAPI app at / (PRD 8A, issue #41).
// In dev (`npm run dev`), API paths are proxied to a local `uvicorn refdesk.api.app:app`,
// so the UI always talks to the real API, which enforces the gates (PRD 8B).
// `npm test` runs component tests in jsdom (issue #43). Two pages: the app at / and the
// design library at /design/ (issue #44); `npm run test:a11y` runs axe on the built library.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const API = "http://127.0.0.1:8000";
const API_PATHS = ["/boards", "/runs", "/reports", "/healthz", "/readyz"];

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      // Relative to ui/, where npm runs every script.
      input: { main: "index.html", design: "design/index.html" },
    },
  },
  server: { proxy: Object.fromEntries(API_PATHS.map((path) => [path, API])) },
  test: { environment: "jsdom", setupFiles: ["src/test-setup.ts"], include: ["src/**/*.test.tsx"] },
});
