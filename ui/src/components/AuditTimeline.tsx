// AuditTimeline (design/components/AuditTimeline.md). The run's event log, read-only, in
// the order the log recorded it (never re-sorted here: the log order is the record). Each
// dot's colour is repeated as a word in the heading. Versions and the config hash belong
// to the audit view only, so this component is where they appear.
import { Icon, type IconName } from "./Icon";
import "./AuditTimeline.css";

export type EventTone = "ok" | "warn" | "danger" | "neutral";

export interface AuditEvent {
  at: string; // ISO 8601, as logged
  label: string; // the state in words: "Verified", "Flagged", "Stopped"
  tone: EventTone;
  what: string;
  tool?: string;
  tokens?: number;
  cost_usd?: number;
  reason_code?: string;
}

export interface AuditTimelineProps {
  events: AuditEvent[];
  versions?: Record<string, string>; // model, adapter and config versions, config hash
}

const ICON: Record<EventTone, IconName> = { ok: "check", warn: "alert", danger: "alert", neutral: "circle" };

function meta(event: AuditEvent): string {
  const parts = [
    event.tool && `tool=${event.tool}`,
    event.tokens !== undefined && `tokens=${event.tokens}`,
    event.cost_usd !== undefined && `cost=USD ${event.cost_usd.toFixed(4)}`,
    event.reason_code && `reason=${event.reason_code}`,
  ];
  return parts.filter(Boolean).join(" · ");
}

export function AuditTimeline({ events, versions }: AuditTimelineProps) {
  return (
    <section className="rd-audit" aria-label="Run audit log">
      {versions && Object.keys(versions).length > 0 && (
        <dl className="rd-audit-versions">
          {Object.entries(versions).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {events.length === 0 ? (
        <p className="rd-audit-empty">No events recorded yet.</p>
      ) : (
        <ol className="rd-audit-list">
          {events.map((event, index) => (
            <li key={`${event.at}-${index}`} className={`rd-audit-event rd-audit-event--${event.tone}`}>
              <span className="rd-audit-dot" aria-hidden="true">
                <Icon name={ICON[event.tone]} />
              </span>
              <div>
                <h4 className="rd-audit-heading">
                  <time dateTime={event.at}>{event.at}</time> <span className="rd-audit-label">{event.label}</span>
                </h4>
                <p className="rd-audit-what">{event.what}</p>
                {meta(event) && <p className="rd-audit-meta">{meta(event)}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
