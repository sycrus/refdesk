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
  if (options.reproduction) await page.getByRole("radio", { name: /^In something you'll publish/ }).check();
  await page.getByRole("button", { name: "Find references" }).click();
  await expect(page).toHaveURL(/\?run=run-/);
}

// Keep every work on the shortlist (issue 231): a work nobody kept is not reviewed,
// approved or exported. "Saved" appears only after the API confirms each change. Keep is
// the ✓ on each image tile (issue 232).
async function keepAll(page: Page) {
  const keeps = page.getByRole("list", { name: "References" }).getByRole("button", { name: /^Keep / });
  await expect(keeps.first()).toBeAttached();
  const count = await keeps.count();
  await page.getByLabel("Your name (recorded with what you keep)").fill("Joe");
  for (let i = 0; i < count; i++) {
    await keeps.nth(i).click(); // pressed once the API confirms, not on click
    await expect(page.getByText(new RegExp(`^${i + 1} of ${count} kept\\. Saved `))).toBeVisible();
  }
}

// The Shortlist opens on Images (issue 232); the detailed cards are the Full view.
async function showFull(page: Page) {
  await page.getByRole("radio", { name: "Full" }).check();
}

test("creates a board and shows S3 with a rationale, both badges and evidence", async ({ page }) => {
  await newBoard(page, "cypresses in a landscape");
  await showFull(page);
  const card = page.getByRole("article").filter({ hasText: "Wheat Field with Cypresses" });
  await expect(card).toBeVisible();
  // The mock generator writes claims from the record; the mock judge supports them (#98).
  await expect(card.getByText(/The record gives the artist as Vincent van Gogh/)).toBeVisible();
  await expect(card.getByText("Attribution verified from record")).toBeVisible();
  await expect(card.getByText("Open (as stated by source)")).toBeVisible();
  await expect(card.getByRole("link", { name: /subject_tags Cypresses/ })).toBeVisible();
  await expect(card.getByText(/^Score /)).toBeVisible();
  await expect(page.getByText("mock, mock-judge")).toBeVisible();
  await expect(page.getByRole("list", { name: "Stages of this board" })).toBeVisible(); // the gates, in the stage panel (issue 229)
});

test("reference-only shows every rights status; permission required has no image", async ({ page }) => {
  await newBoard(page, "oil");
  await showFull(page);
  await expect(page.getByRole("article")).toHaveCount(3);
  const locked = page.getByRole("article").filter({ hasText: "Permission required" }).first();
  await expect(locked.getByRole("img")).toHaveCount(0);
  await expect(locked.getByRole("link", { name: "View the museum record" })).toBeVisible();
});

test("reproduction mode shows only works the source states are open", async ({ page }) => {
  await newBoard(page, "oil", { reproduction: true });
  await showFull(page);
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
    await expect(page.getByRole("list", { name: "References" }).getByRole("listitem")).toHaveCount(3); // Images view
    const s3 = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(
      s3.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
    ).toEqual([]);
  });
}

// S4 item details, now in the lightbox (issues 99 and 232): opening a work shows the image
// and every section of its evidence; Esc closes it and the board is still there.
for (const colorScheme of ["light", "dark"] as const) {
  test(`the lightbox shows each section and passes axe (${colorScheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    await newBoard(page, "cypresses in a landscape");
    await page.getByRole("button", { name: "Open Wheat Field with Cypresses" }).click();
    await expect(page).toHaveURL(/&item=met%3A436535/);
    const dialog = page.getByRole("dialog", { name: "Wheat Field with Cypresses" });
    await expect(dialog).toBeVisible();
    for (const name of ["Why it fits", "Evidence from the record", "Rights record", "How this result was made"]) {
      await expect(dialog.getByRole("heading", { level: 3, name })).toBeVisible();
    }
    await expect(dialog.getByText(/The record gives the artist as Vincent van Gogh/)).toBeVisible();
    await expect(dialog.getByText("Purchase, The Annenberg Foundation Gift, 1993")).toBeVisible();
    await expect(dialog.getByText("isPublicDomain")).toBeVisible();
    await expect(dialog.getByText("Not computed yet.")).toBeVisible();
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(
      axe.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
    ).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page).not.toHaveURL(/&item=/);
    await expect(page.getByRole("heading", { name: "Board" })).toBeVisible();
  });
}

// Issue 232: shortlist by keyboard in the lightbox. Each work is flagged (the mock judge
// is scripted UNSUPPORTED), so K asks for a note, which is recorded as its G3 decision;
// Verify then shows both decided, and Continue opens Approve.
test.describe("shortlist in the lightbox", () => {
  test.afterEach(async ({ request }) => {
    await request.post("http://127.0.0.1:8100/_mock/script", { data: { script: ["ok"] } });
  });

  test("keep two flagged works with notes by keyboard, verify, continue to Approve", async ({ page, request }) => {
    await request.post("http://127.0.0.1:8100/_mock/script", { data: { script: ["unsupported"] } });
    await newBoard(page, "oil");
    await page.getByRole("list", { name: "References" }).getByRole("button", { name: /^Open / }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await page.keyboard.press("k");
    const form = dialog.getByRole("form", { name: "Keep this work" });
    await form.getByLabel("Your name (recorded with what you keep)").fill("Joe");
    await form.getByLabel(/^Note/).fill("Checked against the Met page.");
    await form.getByRole("button", { name: "Keep with this note" }).click();
    await expect(dialog.getByRole("button", { name: /^Kept/ })).toBeVisible();

    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("k");
    await form.getByLabel(/^Note/).fill("Date confirmed on the record.");
    await form.getByRole("button", { name: "Keep with this note" }).click();
    await expect(dialog.getByRole("button", { name: /^Kept/ })).toBeVisible();

    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(
      axe.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
    ).toEqual([]);

    await page.keyboard.press("Escape");
    await expect(page.getByText(/^2 of 3 kept\. Saved /)).toBeVisible();
    await page.getByRole("button", { name: "Review flagged items (2)" }).click();
    await expect(page.getByRole("main").getByText("All 2 flagged items decided: 2 kept, 0 dropped.")).toBeVisible();
    await page.getByRole("button", { name: "Continue to approval" }).click();
    await expect(page.getByRole("heading", { name: "Approve and export", level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve and export 2 items" })).toBeVisible();
  });
});

// S5 Needs human check (issue #100). The mock judge is scripted to answer UNSUPPORTED for
// this board only, so every item is flagged; board.spec tests run one after another, and the
// script is reset afterwards.
test.describe("S5 review", () => {
  test.afterEach(async ({ request }) => {
    await request.post("http://127.0.0.1:8100/_mock/script", { data: { script: ["ok"] } });
  });

  test("decide every flagged item, then Continue opens approval", async ({ page, request }) => {
    await request.post("http://127.0.0.1:8100/_mock/script", { data: { script: ["unsupported"] } });
    await newBoard(page, "oil");
    await keepAll(page);
    await page.getByRole("button", { name: "Review flagged items (3)" }).click();
    await expect(page).toHaveURL(/&review=1/);
    await expect(page.getByRole("heading", { name: "Needs human check" })).toBeVisible();
    await expect(page.getByText("3 flagged items still need a saved decision.")).toBeVisible();

    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme });
      const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(
        axe.violations
          .filter((v) => v.impact === "serious" || v.impact === "critical")
          .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
      ).toEqual([]);
    }

    await page.getByLabel("Your name (recorded with each decision)").fill("Joe");
    const items = page.getByRole("list", { name: "Flagged items" }).getByRole("group");
    await items.nth(0).getByLabel("Keep", { exact: true }).check();
    await items.nth(0).getByLabel("Note (required to keep)").fill("Checked against the Met page.");
    await items.nth(1).getByLabel("Drop", { exact: true }).check();
    await items.nth(2).getByLabel("Drop", { exact: true }).check();
    await page.getByRole("button", { name: "Save decisions" }).click();
    await expect(page.getByRole("main").getByText("All 3 flagged items decided: 1 kept, 2 dropped.")).toBeVisible();

    await page.getByRole("button", { name: "Continue to approval" }).click();
    await expect(page.getByRole("heading", { name: "Approve and export", level: 1 })).toBeVisible();
    await expect(page.getByRole("main").getByText("Ready for approval.")).toBeVisible();
    // One item was kept with a note, two dropped: the pack holds one.
    await expect(page.getByRole("button", { name: "Approve and export 1 item" })).toBeVisible();
  });
});

// S7 Run history and audit (issue 159): the runs list with a redacted brief and where it
// was sent, then one run's events. Read-only.
test("S7 lists past runs, opens one run's events, and passes axe", async ({ page }) => {
  await newBoard(page, "cypresses in a landscape");
  const runId = new URL(page.url()).searchParams.get("run")!;
  // Wait for the run to finish, so the history shows its final sent_to.
  await expect(page.getByText("mock, mock-judge")).toBeVisible();
  await page.getByRole("link", { name: "Run history" }).click();
  await expect(page).toHaveURL(/\?history=1/);
  await expect(page.getByRole("heading", { level: 1, name: "Run history" })).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: runId });
  await expect(row).toBeVisible();
  await expect(row.getByText("[brief redacted]")).toBeVisible();
  await expect(row.getByText("mock, mock-judge")).toBeVisible();
  await expect(page.getByText("cypresses in a landscape")).toHaveCount(0);
  await expect(page.getByRole("main").getByRole("button")).toHaveCount(0); // read-only; the panel's toggle is outside main

  const axe = async () => {
    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme });
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(
        result.violations
          .filter((v) => v.impact === "serious" || v.impact === "critical")
          .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
      ).toEqual([]);
    }
  };
  await axe();

  await row.getByRole("link", { name: `Events for ${runId}` }).click();
  await expect(page).toHaveURL(new RegExp(`[?]audit=${runId}`));
  const log = page.getByRole("region", { name: "Run audit log" });
  await expect(log.getByRole("listitem").first()).toBeVisible();
  await expect(page.getByText("mock, mock-judge")).toBeVisible();
  await axe();

  await page.getByRole("link", { name: "Open the board" }).click();
  await expect(page.getByRole("heading", { name: "Board" })).toBeVisible();
});

// The stage panel (issue 229): no board stages on New board; once a board is open, go
// back to Search and check (read-only), then return to the Shortlist where the work is.
test("the stage panel opens an earlier stage and returns to the shortlist", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("list", { name: "Stages of this board" })).toHaveCount(0);
  await newBoard(page, "cypresses in a landscape");
  const stages = page.getByRole("list", { name: "Stages of this board" });
  await expect(stages.getByRole("link", { name: /^Shortlist/ })).toHaveAttribute("aria-current", "step");

  await stages.getByRole("link", { name: /^Search and check/ }).click();
  await expect(page).toHaveURL(/&stage=search/);
  await expect(page.getByRole("heading", { name: "Search and check", level: 1 })).toBeVisible();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Stopped:"); // the stop reason, never hidden
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(
      axe.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
    ).toEqual([]);
  }

  await stages.getByRole("link", { name: /^Brief/ }).click();
  await expect(page.getByRole("heading", { name: "Brief", level: 1 })).toBeVisible();
  await expect(page.getByRole("group", { name: "This board" })).toContainText("Stopped:");

  await stages.getByRole("link", { name: /^Shortlist/ }).click();
  await expect(page.getByRole("list", { name: "References" })).toBeVisible();
  await expect(stages.getByText("Export: pending (G5). Not reached yet.")).toBeAttached();
});

// Issue 234: leave a board mid-shortlist, find it on Boards, reopen it at the Shortlist
// with the kept works intact. Its name comes from the run ID, never the brief.
test("leave a board mid-shortlist, find it on Boards, reopen it with its kept works", async ({ page }) => {
  await newBoard(page, "oil");
  const runId = new URL(page.url()).searchParams.get("run") ?? "";
  await page.getByLabel("Your name (recorded with what you keep)").fill("Joe");
  await page.getByRole("list", { name: "References" }).getByRole("button", { name: /^Keep / }).first().click();
  await expect(page.getByText(/^1 of 3 kept\. Saved automatically/)).toBeVisible();

  await page.getByRole("navigation", { name: "refdesk" }).getByRole("link", { name: "New board" }).click();
  const name = `Board ${runId.replace("run-", "").slice(0, 6)}`;
  await expect(page.getByRole("status").filter({ hasText: `“${name}” is saved as a draft: ready to approve.` })).toBeVisible();

  await page.getByRole("link", { name: "Find it in Boards" }).click();
  await expect(page.getByRole("heading", { name: "Boards", level: 1 })).toBeVisible();
  const card = page.getByRole("list", { name: "Boards" }).getByRole("listitem").filter({ hasText: name });
  await expect(card.getByText("Draft · ready to approve")).toBeVisible(); // one verified work kept
  await expect(card).not.toContainText("oil"); // the brief never appears in the list
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(
      axe.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
    ).toEqual([]);
  }

  await card.getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`[?]run=${runId}$`)); // a draft opens on its Shortlist
  await expect(page.getByText(/^1 of 3 kept\. Saved automatically/)).toBeVisible();
  await expect(page.getByRole("list", { name: "References" }).getByRole("button", { pressed: true })).toHaveCount(1);
});

// S6 Approve and export (issue 101): the ConfirmDialog, the irreversible export, the receipt.
test("approve and export a verified board, then it is read-only", async ({ page }) => {
  await newBoard(page, "cypresses in a landscape");
  await keepAll(page);
  await page.getByRole("button", { name: "Approve and export" }).click();
  await expect(page).toHaveURL(/&approve=1/);
  await expect(page.getByRole("heading", { name: "What the provenance pack will hold" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Open (as stated by source): 1" })).toBeVisible(); // issue 233
  await expect(page.getByRole("region", { name: "Left out: 0" })).toBeVisible();
  await page.getByRole("button", { name: "Approve and export 1 item" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(
      axe.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`),
    ).toEqual([]);
  }
  await dialog.getByLabel("Approving as").fill("Joe");
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Approve and export" }).click();

  await expect(page.getByText("Exported. This board is now read-only")).toBeVisible();
  const stages = page.getByRole("list", { name: "Stages of this board" });
  await expect(stages.getByRole("link", { name: "Export: passed (G5)" })).toBeVisible();
  await expect(page.getByText(/runs\/exports\/run-.*\.csv/)).toBeVisible();
  await page.getByRole("link", { name: "Back to the board" }).click();
  await expect(page.getByRole("link", { name: "See the receipt" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve and export" })).toHaveCount(0);
});

test("the footer links to the disclaimer and terms, which pass axe (issue 219)", async ({ page }) => {
  await page.goto("/");
  const footer = page.getByRole("contentinfo");
  await expect(footer.getByText("Not legal advice.")).toBeVisible();
  await footer.getByRole("link", { name: "Disclaimer and terms" }).click();
  await expect(page).toHaveURL(/\?terms=1/);
  await expect(page.getByRole("heading", { name: "What refdesk does not do" })).toBeVisible();
  await expect(page.getByText(/not been reviewed by a lawyer/)).toBeVisible();
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
});
