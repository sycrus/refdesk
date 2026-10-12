// Accessibility check of the built design library (issue #44): Playwright serves ui/dist
// with `vite preview` and runs axe in headless Chromium. A real browser is needed: in jsdom
// axe cannot compute colours, so it would skip the contrast rules.
import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

export default defineConfig({
  testDir: "e2e",
  reporter: "list",
  // Reduced motion turns off the components' colour transitions, so axe measures colours at
  // rest. Without it, a check run straight after a theme switch catches buttons mid-fade
  // (light card blending into dark card) and reports contrast that no one ever sees settled.
  use: { baseURL: `http://127.0.0.1:${PORT}`, reducedMotion: "reduce" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}/design/`,
    reuseExistingServer: false,
  },
});
