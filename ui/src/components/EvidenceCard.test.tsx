import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { BoardItem } from "../api/types";
import { AttributionStatus, OPINION_FLAGGED, RightsStatus } from "../generated/wording";
import { EvidenceCard } from "./EvidenceCard";

function item(overrides: Partial<BoardItem> = {}, rights = {}): BoardItem {
  return {
    record: {
      id: "met:436535",
      source: "met",
      title: "Wheat Field with Cypresses",
      artist: "Vincent van Gogh",
      date: "1889",
      image_url: "https://images.metmuseum.org/x.jpg",
      record_url: "https://www.metmuseum.org/art/collection/search/436535",
      rights: { status: RightsStatus.OPEN, flag_field: "isPublicDomain", ...rights },
    },
    rationale: "Swirling cypresses against a wheat field.",
    evidence: [{ field: "medium", value: "Oil on canvas" }],
    attribution_status: AttributionStatus.VERIFIED,
    flag_reasons: [],
    selected: false,
    ...overrides,
  };
}

describe("EvidenceCard", () => {
  it("shows an open work's image with alt text from title and artist", () => {
    render(<EvidenceCard item={item()} />);
    expect(screen.getByRole("img").getAttribute("alt")).toBe("Wheat Field with Cypresses, Vincent van Gogh");
  });

  it("shows metadata and a link instead of the image for permission required", () => {
    render(<EvidenceCard item={item({}, { status: RightsStatus.PERMISSION_REQUIRED })} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("link", { name: "View the museum record" })).toBeTruthy();
  });

  it("shows no image for an unverified work, or an 'open' status with no source flag", () => {
    const { unmount } = render(<EvidenceCard item={item({}, { status: RightsStatus.UNVERIFIED })} />);
    expect(screen.queryByRole("img")).toBeNull();
    unmount();
    render(<EvidenceCard item={item({}, { flag_field: null })} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText(RightsStatus.UNVERIFIED)).toBeTruthy(); // never shown as open
  });

  it("shows two separate badges: attribution and rights", () => {
    render(<EvidenceCard item={item()} />);
    expect(screen.getByText(AttributionStatus.VERIFIED)).toBeTruthy();
    expect(screen.getByText(RightsStatus.OPEN)).toBeTruthy();
  });

  it("evidence chips name the record field and link to the museum record", () => {
    render(<EvidenceCard item={item()} />);
    const chip = screen.getByRole("link", { name: "medium Oil on canvas" });
    expect(chip.getAttribute("href")).toBe("https://www.metmuseum.org/art/collection/search/436535");
  });

  it("never invents missing fields", () => {
    render(<EvidenceCard item={item({ rationale: null }, {})} />);
    expect(screen.getByText("No rationale yet.")).toBeTruthy();
  });

  it("shows an opinion flag next to the rationale without changing the badge", () => {
    render(<EvidenceCard item={item({ opinion_flag: OPINION_FLAGGED }, {})} />);
    expect(screen.getByText(OPINION_FLAGGED)).toBeTruthy();
    expect(screen.getByText(AttributionStatus.VERIFIED)).toBeTruthy();
  });

  it("lists why an item needs a human check", () => {
    render(
      <EvidenceCard
        item={item({
          attribution_status: AttributionStatus.NEEDS_HUMAN_CHECK,
          flag_reasons: ["Artist differs from the record"],
        })}
      />,
    );
    expect(screen.getByText("Artist differs from the record")).toBeTruthy();
  });

  it("Keep is a real, labelled checkbox; the actions call back", async () => {
    const onKeepChange = vi.fn();
    const onMoreLikeThis = vi.fn();
    render(<EvidenceCard item={item()} onKeepChange={onKeepChange} onMoreLikeThis={onMoreLikeThis} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Keep" }));
    expect(onKeepChange).toHaveBeenCalledWith(true);
    await userEvent.click(screen.getByRole("button", { name: "More like this" }));
    expect(onMoreLikeThis).toHaveBeenCalledOnce();
  });

  it("a selected card is marked by its border class", () => {
    render(<EvidenceCard item={item({ selected: true })} />);
    expect(screen.getByRole("article").className).toContain("rd-card--selected");
  });

  it("drops non-http(s) URLs from museum data", () => {
    const hostile = item({ evidence: [{ field: "medium", value: "Oil", record_url: "javascript:alert(1)" }] });
    hostile.record.record_url = "javascript:alert(1)";
    hostile.record.image_url = "data:image/png;base64,AAAA";
    render(<EvidenceCard item={hostile} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryAllByRole("link")).toEqual([]);
    expect(document.querySelector(".rd-chip")?.textContent).toBe("medium Oil"); // still shown, unlinked
  });

  it("shows the score and the parts that sum to it", () => {
    render(<EvidenceCard item={item({ score: 0.276, score_components: { similarity: 0.176, attributes: 0.1 } })} />);
    expect(screen.getByText("Score 0.276 = similarity 0.176 + attributes 0.100")).toBeTruthy();
  });
});
