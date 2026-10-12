// axe on /design (issue #44): zero serious or critical violations, in both themes and with
// the approval dialog open. Run `npm run build` first; `npm run test:e2e` starts the API, which serves the build.
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const COMPONENTS = [
  "Button",
  "StatusBadge",
  "EvidenceCard",
  "GateStepper",
  "CostMeter",
  "StopBanner",
  "ConfirmDialog",
  "AuditTimeline",
];

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => `${n.target.join(" ")}: ${n.failureSummary}`).join("; ")}`);
}

test("shows all 8 components", async ({ page }) => {
  await page.goto("/design/");
  for (const name of COMPONENTS) {
    await expect(page.getByRole("heading", { level: 2, name, exact: true })).toBeVisible();
  }
});

for (const theme of ["Light", "Dark"]) {
  test(`no serious or critical axe violations: ${theme.toLowerCase()} theme`, async ({ page }) => {
    await page.goto("/design/");
    await page.getByRole("radio", { name: theme }).check();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme.toLowerCase());
    expect(await seriousViolations(page)).toEqual([]);
  });

  test(`no serious or critical axe violations with the dialog open: ${theme.toLowerCase()} theme`, async ({
    page,
  }) => {
    await page.goto("/design/");
    await page.getByRole("radio", { name: theme }).check();
    await page.getByRole("button", { name: "Open the approval dialog" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });
}
