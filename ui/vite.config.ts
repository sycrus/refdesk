// Built to ui/dist and served by the FastAPI app at / (PRD 8A, issue #41).
// In dev (`npm run dev`), API paths are proxied to a local `uvicorn refdesk.api.app:app`,
// so the UI always talks to the real API, which enforces the gates (PRD 8B).
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API = "http://127.0.0.1:8000";
const API_PATHS = ["/boards", "/runs", "/reports", "/healthz", "/readyz"];

export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: { proxy: Object.fromEntries(API_PATHS.map((path) => [path, API])) },
});
