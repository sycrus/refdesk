import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AttributionStatus, RightsStatus } from "../generated/wording";
import { StatusBadge } from "./StatusBadge";

function iconFor(label: string) {
  return screen.getByText(label).parentElement?.querySelector("svg")?.dataset.icon;
}

describe("StatusBadge", () => {
  it("shows verified attribution with a check and the fixed label", () => {
    render(<StatusBadge kind="attribution" status={AttributionStatus.VERIFIED} />);
    expect(iconFor(AttributionStatus.VERIFIED)).toBe("check");
  });

  it("never shows an inferred attribution as verified", () => {
    render(<StatusBadge kind="attribution" status={AttributionStatus.VERIFIED} inferred />);
    expect(screen.queryByText(AttributionStatus.VERIFIED)).toBeNull();
    expect(iconFor(AttributionStatus.NEEDS_HUMAN_CHECK)).toBe("alert");
  });

  it("never shows an inferred open status as open", () => {
    render(<StatusBadge kind="rights" status={RightsStatus.OPEN} inferred />);
    expect(screen.queryByText(RightsStatus.OPEN)).toBeNull();
    expect(iconFor(RightsStatus.UNVERIFIED)).toBe("alert");
  });

  it("shows permission required with a lock, even when inferred", () => {
    render(<StatusBadge kind="rights" status={RightsStatus.PERMISSION_REQUIRED} inferred />);
    expect(iconFor(RightsStatus.PERMISSION_REQUIRED)).toBe("lock");
  });

  it("maps an unrecognised value to the cautious label, never to verified or open", () => {
    render(
      <>
        <StatusBadge kind="attribution" status="Looks right to me" />
        <StatusBadge kind="rights" status="open" />
      </>,
    );
    expect(screen.getByText(AttributionStatus.NEEDS_HUMAN_CHECK)).toBeTruthy();
    expect(screen.getByText(RightsStatus.UNVERIFIED)).toBeTruthy();
  });

  it("always pairs the label with an icon", () => {
    for (const status of Object.values(RightsStatus)) {
      const { unmount } = render(<StatusBadge kind="rights" status={status} />);
      expect(iconFor(status)).toBeTruthy();
      unmount();
    }
  });
});
