// Issue 218: the old usage labels described the mechanism and confused readers. No
// user-facing source may still use them; the API values (reference_only, reproduction)
// are not user-facing and stay. Sources are read through Vite (import.meta.glob), so the
// test needs no Node type definitions.
import { describe, expect, it } from "vitest";

const SOURCES = import.meta.glob(["../**/*.ts", "../**/*.tsx", "!../**/*.test.tsx", "!../generated/**"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("usage wording", () => {
  it("no user-facing source uses the old labels", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(10); // the glob found the sources
    const offenders = Object.entries(SOURCES)
      .filter(([, text]) => /"Reference only|"Reproduction|> ?Reference only|> ?Reproduction/.test(text))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
