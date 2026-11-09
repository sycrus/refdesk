import { afterEach, describe, expect, it, vi } from "vitest";
import { applyAppearance, setAppearance, storedAppearance } from "./theme";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  vi.restoreAllMocks();
});

describe("appearance (issue 228)", () => {
  it("defaults to matching the computer, with no data-theme", () => {
    expect(storedAppearance()).toBe("system");
    applyAppearance(storedAppearance());
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("stores and applies a forced theme, and system removes it again", () => {
    setAppearance("dark");
    expect(storedAppearance()).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    setAppearance("system");
    expect(storedAppearance()).toBe("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("ignores a stored value it does not recognise", () => {
    localStorage.setItem("refdesk-appearance", "sepia");
    expect(storedAppearance()).toBe("system");
  });

  it("still applies the choice when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    setAppearance("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
