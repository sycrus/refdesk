// The /design library (PRD 8A, issue #44): every component in every documented state, in
// the theme chosen at the top. CI runs axe on this page in both themes, so an accessibility
// regression in any component fails the build before a screen uses it.
//
// All data here is invented sample data, marked as such. None of it is a real record.
import { type ReactNode, useEffect, useState } from "react";
import type { BoardItem, Gate } from "../api/types";
import { AuditTimeline } from "../components/AuditTimeline";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { CostMeter } from "../components/CostMeter";
import { EvidenceCard } from "../components/EvidenceCard";
import { GateStepper } from "../components/GateStepper";
import { StatusBadge } from "../components/StatusBadge";
import { StopBanner } from "../components/StopBanner";
import { AttributionStatus, RightsStatus, StopReason } from "../generated/wording";
import "./DesignLibrary.css";

type Theme = "system" | "light" | "dark";

function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    const html = document.documentElement;
    if (theme === "system") delete html.dataset.theme;
    else html.dataset.theme = theme;
  }, [theme]);
  return [theme, setTheme];
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="dl-section" aria-labelledby={id}>
      <h2 id={id} className="dl-section-title">
        {title}
      </h2>
      {children}
    </section>
  );
}

function State({ name, children }: { name: string; children: ReactNode }) {
  return (
    <figure className="dl-state">
      <figcaption>{name}</figcaption>
      <div className="dl-state-body">{children}</div>
    </figure>
  );
}

const SAMPLE_IMAGE = () => `${window.location.origin}/design/sample-artwork.svg`;

function sampleItem(overrides: Partial<BoardItem> = {}, rights: Partial<BoardItem["record"]["rights"]> = {}): BoardItem {
  return {
    record: {
      id: "sample:1",
      source: "sample",
      title: "Sample work (placeholder)",
      artist: "Sample artist",
      date: "1650",
      image_url: SAMPLE_IMAGE(),
      record_url: "https://example.org/sample-record",
      rights: { status: RightsStatus.OPEN, flag_field: "isPublicDomain", ...rights },
    },
    rationale: "Sample rationale: a low horizon and a pale sky, as the brief asks.",
    evidence: [
      { field: "medium", value: "Oil on canvas" },
      { field: "date", value: "1650" },
    ],
    attribution_status: AttributionStatus.VERIFIED,
    flag_reasons: [],
    selected: false,
    ...overrides,
  };
}

const IN_REVIEW: Gate[] = [
  { id: "G0", state: "passed", status_text: "Brief accepted." },
  { id: "G1", state: "passed", status_text: "USD 0.012 of 0.050." },
  { id: "G2", state: "passed", status_text: "12 checked, 2 flagged." },
  { id: "G3", state: "active", status_text: "2 items to review.", actor: "operator" },
  { id: "G4", state: "pending", status_text: "Waiting for review.", actor: "approver" },
  { id: "G5", state: "pending", status_text: "Not exported.", actor: "approver" },
];

const BLOCKED: Gate[] = [
  { id: "G0", state: "passed", status_text: "Brief accepted." },
  { id: "G1", state: "blocked", status_text: "Budget cap reached." },
  { id: "G2", state: "skipped", status_text: "Not reached." },
  { id: "G3", state: "pending", status_text: "Not reached.", actor: "operator" },
  { id: "G4", state: "pending", status_text: "Not reached.", actor: "approver" },
  { id: "G5", state: "pending", status_text: "Not exported.", actor: "approver" },
];

const EXPORTED: Gate[] = IN_REVIEW.map((gate) => ({ ...gate, state: "passed", status_text: "Done." }));

export function DesignLibrary() {
  const [theme, setTheme] = useTheme();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [kept, setKept] = useState(true);

  return (
    <main className="dl">
      <header className="dl-header">
        <h1>Design library</h1>
        <p>Every component in every documented state. All data on this page is invented sample data.</p>
        <fieldset className="dl-theme">
          <legend>Theme</legend>
          {(["system", "light", "dark"] as const).map((option) => (
            <label key={option}>
              <input
                type="radio"
                name="theme"
                value={option}
                checked={theme === option}
                onChange={() => setTheme(option)}
              />
              {option === "system" ? "System" : option === "light" ? "Light" : "Dark"}
            </label>
          ))}
        </fieldset>
      </header>

      <Section id="button" title="Button">
        <State name="Primary">
          <Button variant="primary">Approve and export</Button>
        </State>
        <State name="Secondary">
          <Button>Cancel</Button>
        </State>
        <State name="Ghost">
          <Button variant="ghost">More like this</Button>
        </State>
        <State name="Danger">
          <Button variant="danger">Export and lock board</Button>
        </State>
        <State name="Disabled, with its reason">
          <Button variant="primary" disabledReason="Tick the acknowledgement to continue.">
            Approve and export
          </Button>
        </State>
      </Section>

      <Section id="status-badge" title="StatusBadge">
        <State name="Attribution verified">
          <StatusBadge kind="attribution" status={AttributionStatus.VERIFIED} />
        </State>
        <State name="Attribution needs a check">
          <StatusBadge kind="attribution" status={AttributionStatus.NEEDS_HUMAN_CHECK} />
        </State>
        <State name="Attribution inferred (shown as needs a check)">
          <StatusBadge kind="attribution" status={AttributionStatus.VERIFIED} inferred />
        </State>
        <State name="Rights open">
          <StatusBadge kind="rights" status={RightsStatus.OPEN} />
        </State>
        <State name="Rights unverified">
          <StatusBadge kind="rights" status={RightsStatus.UNVERIFIED} />
        </State>
        <State name="Rights permission required">
          <StatusBadge kind="rights" status={RightsStatus.PERMISSION_REQUIRED} />
        </State>
      </Section>

      <Section id="evidence-card" title="EvidenceCard">
        <div className="dl-grid">
          <State name="Open and verified, kept">
            <EvidenceCard
              item={sampleItem({ selected: kept })}
              onMoreLikeThis={() => undefined}
              onReport={() => undefined}
              onKeepChange={setKept}
            />
          </State>
          <State name="Needs a human check">
            <EvidenceCard
              item={sampleItem({
                record: { ...sampleItem().record, id: "sample:2" },
                attribution_status: AttributionStatus.NEEDS_HUMAN_CHECK,
                flag_reasons: ["Sample reason: the artist differs from the record."],
              })}
              onReport={() => undefined}
            />
          </State>
          <State name="Permission required (no image)">
            <EvidenceCard item={sampleItem({}, { status: RightsStatus.PERMISSION_REQUIRED })} />
          </State>
          <State name="No rationale yet">
            <EvidenceCard item={sampleItem({ rationale: null, evidence: [] }, { status: RightsStatus.UNVERIFIED })} />
          </State>
        </div>
      </Section>

      <Section id="gate-stepper" title="GateStepper">
        <State name="In review">
          <GateStepper gates={IN_REVIEW} onSelect={() => undefined} />
        </State>
        <State name="Blocked at spend">
          <GateStepper gates={BLOCKED} />
        </State>
        <State name="Exported (all passed)">
          <GateStepper gates={EXPORTED} />
        </State>
      </Section>

      <Section id="cost-meter" title="CostMeter">
        <State name="Normal">
          <CostMeter spent={0.012} cap={0.05} />
        </State>
        <State name="Warning (80% or more)">
          <CostMeter spent={0.042} cap={0.05} />
        </State>
        <State name="Blocked (cap reached)">
          <CostMeter spent={0.05} cap={0.05} />
        </State>
      </Section>

      <Section id="stop-banner" title="StopBanner">
        <State name="Budget cap (danger)">
          <StopBanner
            reason={StopReason.BUDGET_CAP}
            accepted={9}
            target={12}
            actions={
              <>
                <Button variant="primary">Raise the cap</Button>
                <Button>Keep the partial board</Button>
              </>
            }
          />
        </State>
        <State name="Timeout (warning)">
          <StopBanner reason={StopReason.TIMEOUT} accepted={4} target={12} actions={<Button>Relax conditions</Button>} />
        </State>
        <State name="Request declined (danger)">
          <StopBanner reason={StopReason.DECLINED} accepted={0} target={12} />
        </State>
      </Section>

      <Section id="confirm-dialog" title="ConfirmDialog">
        <State name="Closed; opens on demand">
          <Button variant="primary" onClick={() => setDialogOpen(true)}>
            Open the approval dialog
          </Button>
        </State>
        <ConfirmDialog
          open={dialogOpen}
          itemCount={7}
          countsByStatus={{ [RightsStatus.OPEN]: 6, [RightsStatus.UNVERIFIED]: 1 }}
          reviewed={[{ id: "sample:2", title: "Sample work", note: "Sample note: checked by hand." }]}
          excludedUnverified={2}
          runId="sample-run"
          onConfirm={() => setDialogOpen(false)}
          onCancel={() => setDialogOpen(false)}
        />
      </Section>

      <Section id="audit-timeline" title="AuditTimeline">
        <State name="A run with events">
          <AuditTimeline
            versions={{ config_hash: "sample-hash", model: "sample-model" }}
            events={[
              { at: "2026-01-01T10:00:00Z", label: "Started", tone: "neutral", what: "Sample run started." },
              { at: "2026-01-01T10:00:02Z", label: "Verified", tone: "ok", what: "sample:1 matches the record.", tool: "verifier", tokens: 412, cost_usd: 0.0004 },
              { at: "2026-01-01T10:00:03Z", label: "Flagged", tone: "warn", what: "sample:2 artist differs.", reason_code: "attribution_mismatch" },
              { at: "2026-01-01T10:00:09Z", label: "Stopped", tone: "danger", what: "Budget cap reached.", reason_code: "budget_cap" },
            ]}
          />
        </State>
        <State name="Empty">
          <AuditTimeline events={[]} />
        </State>
      </Section>
    </main>
  );
}
