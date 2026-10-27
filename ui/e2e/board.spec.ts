// S1 -> S2 -> S3 against the real API (issue #46). The store holds three recorded Met
// works: Van Gogh's Wheat Field with Cypresses (open) and two that need permission.
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // Offline and deterministic: never fetch museum images during tests.
  await page.route("https://images.metmuseum.org/**", (route) => route.abort());
});

async function newBoard(page: Page, brief: string, options: { reproduction?: boolean } = {}) {
  await page.goto("/");
  await page.getByLabel("Brief", { exact: true }).fill(brief);
  if (options.reproduction) await page.getByRole("radio", { name: /^Reproduction/ }).check();
  await page.getByRole("button", { name: "Find references" }).click();
  await expect(page).toHaveURL(/\?run=run-/);
}

test("creates a board and shows S3 with a rationale, both badges and evidence", async ({ page }) => {
  await newBoard(page, "cypresses in a landscape");
  const card = page.getByRole("article").filter({ hasText: "Wheat Field with Cypresses" });
  await expect(card).toBeVisible();
  // The mock generator writes claims from the record; the mock judge supports them (#98).
  await expect(card.getByText(/The record gives the artist as Vincent van Gogh/)).toBeVisible();
  await expect(card.getByText("Attribution verified from record")).toBeVisible();
  await expect(card.getByText("Open (as stated by source)")).toBeVisible();
  await expect(card.getByRole("link", { name: /subject_tags Cypresses/ })).toBeVisible();
  await expect(card.getByText(/^Score /)).toBeVisible();
  await expect(page.getByText("mock, mock-judge")).toBeVisible();
  await expect(page.getByRole("list", { name: "Approval gates" })).toBeVisible();
});

test("reference-only shows every rights status; permission required has no image", async ({ page }) => {
  await newBoard(page, "oil");
  await expect(page.getByRole("article")).toHaveCount(3);
  const locked = page.getByRole("article").filter({ hasText: "Permission required" }).first();
  await expect(locked.getByRole("img")).toHaveCount(0);
  await expect(locked.getByRole("link", { name: "View the museum record" })).toBeVisible();
});

test("reproduction mode shows only works the source states are open", async ({ page }) => {
  await newBoard(page, "oil", { reproduction: true });
  await expect(page.getByRole("article")).toHaveCount(1);
  await expect(page.getByRole("article")).toContainText("Wheat Field with Cypresses");
});

test("a board with no results shows the stop reason and its detail", async ({ page }) => {
  await newBoard(page, "zeppelins");
  await expect(page.getByRole("heading", { name: "Stopped: no candidates left" })).toBeVisible();
  await expect(page.getByText("No record matched the brief, conditions and rights filter.")).toBeVisible();
  await expect(page.getByText("0 of 12 items accepted. Nothing was exported.")).toBeVisible();
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`S1 and S3 have no serious or critical axe violations (${colorScheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    await page.goto("/");
    const s1 = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(s1.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
    await newBoard(page, "oil");
    await expect(page.getByRole("article")).toHaveCount(3);
    const s3 = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(
      s3.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
    ).toEqual([]);
  });
}
