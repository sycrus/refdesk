// Browser tests (issues #44, #46) against the real API: Playwright starts the FastAPI app,
// which serves the built UI (ui/dist) and /design/. The store is rebuilt from the recorded
// Met fixtures (scripts/make_e2e_store.py), offline, and the retriever is Jaccard, because
// CI cannot load CLIP. Run `npm run build` first.
import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;
const STORE = "runs/e2e/store.sqlite"; // relative to the repo root (uv runs from there)

export default defineConfig({
  testDir: "e2e",
  reporter: "list",
  // Reduced motion turns off the components' colour transitions, so axe measures colours at
  // rest. Without it, a check run straight after a theme switch catches buttons mid-fade
  // (light card blending into dark card) and reports contrast that no one ever sees settled.
  use: { baseURL: `http://127.0.0.1:${PORT}`, reducedMotion: "reduce" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command:
      `uv run --directory .. python scripts/make_e2e_store.py ${STORE} && ` +
      `uv run --directory .. uvicorn refdesk.api.app:app --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/healthz`,
    env: { REFDESK_DB: STORE, REFDESK_RETRIEVER: "jaccard" },
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
