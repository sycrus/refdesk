// The landing page (issue 230): one prompt with one action, and it fits one screen with
// Options closed (PRD 8A S1).
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SIZES = [
  { width: 1440, height: 900 },
  { width: 1280, height: 720 },
  { width: 1280, height: 600 },
  { width: 390, height: 800 },
];

for (const size of SIZES) {
  test(`fits ${size.width}x${size.height} without scrolling`, async ({ page }) => {
    await page.setViewportSize(size);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "What do you need references for?", level: 1 })).toBeVisible();
    const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollHeight, window.innerHeight]);
    expect(scroll).toBeLessThanOrEqual(inner);
  });
}

test("Find references waits for a brief; an example fills it; Options counts what is set", async ({ page }) => {
  await page.goto("/");
  const find = page.getByRole("button", { name: "Find references" });
  await expect(find).toHaveAttribute("aria-disabled", "true");
  await page.getByRole("button", { name: "Botanical wallpaper for a café, calm greens" }).click();
  await expect(page.getByLabel("Brief", { exact: true })).toHaveValue("Botanical wallpaper for a café, calm greens");
  await expect(find).not.toHaveAttribute("aria-disabled", "true");

  const options = page.getByRole("button", { name: /^Options/ });
  await expect(options).toHaveAttribute("aria-expanded", "false");
  await options.click();
  await page.getByLabel("Period").fill("17th century");
  await page.getByLabel(/^Avoid/).fill("red");
  await expect(options).toHaveAccessibleName("Options 2 set");

  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(
      axe.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
    ).toEqual([]);
  }

  await find.click();
  await expect(page).toHaveURL(/\?run=run-/);
});
