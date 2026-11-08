// The public demo's front page (ADR-025): what refdesk does, what to look at, and the
// recorded example boards. Read-only: it lists runs and reads each one. Copy is in
// content/demo.ts.
import { useEffect, useState } from "react";
import { ApiError, getRun, listRuns } from "../api/client";
import type { RunView } from "../api/types";
import { showsImage } from "../components/EvidenceCard";
import { safeUrl } from "../components/safeUrl";
import {
  DEMO_BOARDS_HEADING,
  DEMO_CODE_LINK,
  DEMO_HOW_HEADING,
  DEMO_LEAD,
  DEMO_POINTS,
  DEMO_TITLE,
  demoHowText,
} from "../content/demo";
import { AttributionStatus, USAGE_INSPIRATION, USAGE_PUBLISH } from "../generated/wording";
import "./screens.css";

const THUMBNAILS = 4;

export interface DemoHomeProps {
  onOpenRun: (runId: string) => void;
}

function flagged(run: RunView): number {
  return run.items.filter((item) => item.attribution_status !== AttributionStatus.VERIFIED).length;
}

function counts(run: RunView): string {
  const works = `${run.items.length} ${run.items.length === 1 ? "work" : "works"}`;
  const n = flagged(run);
  if (n === 0) return `${works}, every attribution verified from the record`;
  return `${works}, ${n} ${n === 1 ? "needs" : "need"} a human check`;
}

function BoardCard({ run, onOpen }: { run: RunView; onOpen: () => void }) {
  const brief = run.request?.brief ?? run.run_id;
  const href = `?run=${encodeURIComponent(run.run_id)}`;
  const images = run.items.filter(showsImage).slice(0, THUMBNAILS);
  return (
    <article className="rd-demo-board" aria-label={brief}>
      {images.length > 0 && (
        <div className="rd-demo-thumbs">
          {images.map((item) => (
            <img
              key={item.record.id}
              src={safeUrl(item.record.image_url)}
              alt={[item.record.title, item.record.artist].filter(Boolean).join(", ")}
              loading="lazy"
            />
          ))}
        </div>
      )}
      <h3 className="rd-demo-brief">{brief}</h3>
      <p className="rd-card-meta">
        {run.request?.usage_mode === "reproduction" ? USAGE_PUBLISH : USAGE_INSPIRATION}
        {" · "}
        {counts(run)}
      </p>
      <a
        className="rd-demo-open"
        href={href}
        onClick={(event) => {
          event.preventDefault();
          onOpen();
        }}
      >
        Open board<span className="rd-visually-hidden">: {brief}</span>
      </a>
    </article>
  );
}

export function DemoHome({ onOpenRun }: DemoHomeProps) {
  const [runs, setRuns] = useState<RunView[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listRuns()
      .then((summaries) => Promise.all(summaries.map((summary) => getRun(summary.run_id))))
      .then((views) => !cancelled && setRuns(views))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, []);

  const generator = runs?.find((run) => run.models_used?.generator)?.models_used?.generator;
  const judge = runs?.find((run) => run.models_used?.judge)?.models_used?.judge;

  return (
    <section className="rd-screen rd-demo" aria-labelledby="demo-title">
      <header className="rd-demo-hero">
        <h1 id="demo-title" className="rd-demo-title">
          {DEMO_TITLE}
        </h1>
        <p className="rd-demo-lead">{DEMO_LEAD}</p>
      </header>

      <section aria-labelledby="demo-boards">
        <h2 id="demo-boards">{DEMO_BOARDS_HEADING}</h2>
        {error && (
          <p className="rd-error" role="alert">
            The example boards did not load: {error}
          </p>
        )}
        {!runs && !error && <p role="status">Loading the example boards…</p>}
        {runs && (
          <div className="rd-demo-boards">
            {runs.map((run) => (
              <BoardCard key={run.run_id} run={run} onOpen={() => onOpenRun(run.run_id)} />
            ))}
          </div>
        )}
      </section>

      <ul className="rd-demo-points" aria-label="What to look at">
        {DEMO_POINTS.map((point) => (
          <li key={point.heading}>
            <h2>{point.heading}</h2>
            <p>{point.text}</p>
          </li>
        ))}
      </ul>

      {runs && (
        <section aria-labelledby="demo-how" className="rd-demo-how">
          <h2 id="demo-how">{DEMO_HOW_HEADING}</h2>
          <p>{demoHowText(generator ?? "a local model", judge ?? "a local judge")}</p>
          <p>
            <a href={DEMO_CODE_LINK.href}>{DEMO_CODE_LINK.text}</a>
          </p>
        </section>
      )}
    </section>
  );
}
