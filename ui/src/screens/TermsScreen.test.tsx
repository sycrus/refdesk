// Issue 219: the disclaimer and terms page, and the footer link on every screen.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { TERMS, TERMS_TITLE } from "../content/terms";
import { NOT_LEGAL_ADVICE, USAGE_INSPIRATION, USAGE_PUBLISH } from "../generated/wording";
import { TermsScreen } from "./TermsScreen";

afterEach(() => {
  window.history.pushState(null, "", "/");
  vi.unstubAllGlobals();
});

function pageText(): string {
  render(<TermsScreen />);
  return screen.getByRole("article", { name: TERMS_TITLE }).textContent ?? "";
}

describe("TermsScreen", () => {
  it("shows every section under its heading", () => {
    render(<TermsScreen />);
    for (const section of TERMS.sections) {
      expect(screen.getByRole("heading", { name: section.heading })).toBeDefined();
    }
  });

  it("states the limits from issue 217: no authentication, no generation, no style clearance", () => {
    const text = pageText();
    expect(text).toMatch(/does not authenticate/);
    expect(text).toMatch(/does not generate images/);
    expect(text).toMatch(/does not clear new work made .in the style of/);
  });

  it("says rights are as stated by the source and not legal advice", () => {
    const text = pageText();
    expect(text).toContain(NOT_LEGAL_ADVICE);
    expect(text).toMatch(/does not verify it independently/);
  });

  it("names both usage choices with the S1 wording", () => {
    const text = pageText();
    expect(text).toContain(USAGE_INSPIRATION);
    expect(text).toContain(USAGE_PUBLISH);
  });

  it("says no lawyer has reviewed it yet and when it was updated", () => {
    const text = pageText();
    expect(text).toMatch(/not been reviewed by a lawyer/);
    expect(text).toContain(TERMS.updated);
  });
});

describe("footer", () => {
  it("links to the terms from the first screen and opens them", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<App />);
    const footer = screen.getByRole("contentinfo");
    await userEvent.click(within(footer).getByRole("link", { name: TERMS_TITLE }));
    expect(window.location.search).toBe("?terms=1");
    expect(screen.getByRole("article", { name: TERMS_TITLE })).toBeDefined();
  });

  it("stays on a run screen too", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    window.history.pushState(null, "", "?run=run-1");
    render(<App />);
    expect(within(screen.getByRole("contentinfo")).getByRole("link", { name: TERMS_TITLE })).toBeDefined();
  });
});
