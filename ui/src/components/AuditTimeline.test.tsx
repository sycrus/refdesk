import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { type AuditEvent, AuditTimeline } from "./AuditTimeline";

const EVENTS: AuditEvent[] = [
  { at: "2026-10-12T10:00:02Z", label: "Verified", tone: "ok", what: "met:1 attribution matches the record.", tool: "verifier", tokens: 412, cost_usd: 0.0004 },
  { at: "2026-10-12T10:00:01Z", label: "Flagged", tone: "warn", what: "met:2 artist differs.", reason_code: "attribution_mismatch" },
  { at: "2026-10-12T10:00:05Z", label: "Exported", tone: "neutral", what: "Exported by Joe." },
];

describe("AuditTimeline", () => {
  it("keeps the log order, without re-sorting by time", () => {
    render(<AuditTimeline events={EVENTS} />);
    const whats = screen.getAllByRole("listitem").map((li) => li.querySelector(".rd-audit-what")?.textContent);
    expect(whats).toEqual(EVENTS.map((e) => e.what));
  });

  it("repeats each state as a word in the heading, not only as a colour", () => {
    render(<AuditTimeline events={EVENTS} />);
    expect(screen.getByText("Verified")).toBeTruthy();
    expect(screen.getByText("Flagged")).toBeTruthy();
  });

  it("shows tool, tokens, cost and reason code as metadata", () => {
    render(<AuditTimeline events={EVENTS} />);
    expect(screen.getByText("tool=verifier · tokens=412 · cost=USD 0.0004")).toBeTruthy();
    expect(screen.getByText("reason=attribution_mismatch")).toBeTruthy();
  });

  it("shows versions and the config hash", () => {
    render(<AuditTimeline events={EVENTS} versions={{ config_hash: "3143edb2d314", model: "phi4" }} />);
    expect(screen.getByText("3143edb2d314")).toBeTruthy();
  });

  it("is read-only: no controls", () => {
    render(<AuditTimeline events={EVENTS} />);
    expect(screen.queryAllByRole("button")).toEqual([]);
    expect(screen.queryAllByRole("textbox")).toEqual([]);
  });

  it("says so when nothing is logged yet", () => {
    render(<AuditTimeline events={[]} />);
    expect(screen.getByText("No events recorded yet.")).toBeTruthy();
  });
});
