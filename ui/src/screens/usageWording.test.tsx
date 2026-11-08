// Issue 218: the old usage labels described the mechanism and confused readers. No
// user-facing source may still use them; the API values (reference_only, reproduction)
// are not user-facing and stay.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "generated" ? [] : sources(path);
    return /\.tsx?$/.test(entry.name) && !/\.test\./.test(entry.name) ? [path] : [];
  });
}

describe("usage wording", () => {
  it("no user-facing source uses the old labels", () => {
    const root = join(__dirname, "..");
    const offenders = sources(root).filter((file) =>
      /"Reference only|"Reproduction|> ?Reference only|> ?Reproduction/.test(readFileSync(file, "utf-8")),
    );
    expect(sources(root).length).toBeGreaterThan(10); // the walk found the sources
    expect(offenders).toEqual([]);
  });
});
