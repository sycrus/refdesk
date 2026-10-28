// S8 "This is wrong" (PRD 8A, issue #146): on S4, file a report on one item for Joe's
// review. The API records who and when and changes nothing on the board; this form only
// shows what the API says back, its status or its refusal.
import { useId, useState } from "react";
import { ApiError, reportError } from "../api/client";
import type { ErrorType } from "../api/types";
import { Button } from "../components/Button";
import "./screens.css";

const ERROR_TYPES: { value: ErrorType; label: string }[] = [
  { value: "attribution", label: "Attribution (artist, title or date)" },
  { value: "rights", label: "Rights status or credit line" },
  { value: "irrelevant", label: "Not relevant to the brief" },
  { value: "rationale", label: "Why it fits is wrong" },
];

export interface ReportFormProps {
  runId: string;
  itemId: string;
}

export function ReportForm({ runId, itemId }: ReportFormProps) {
  const ids = { type: useId(), note: useId(), name: useId() };
  const [open, setOpen] = useState(false);
  const [errorType, setErrorType] = useState<ErrorType>("attribution");
  const [note, setNote] = useState("");
  const [reporter, setReporter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [filed, setFiled] = useState<string | null>(null);

  if (!open) {
    return (
      <Button variant="ghost" onClick={() => setOpen(true)}>
        This is wrong
      </Button>
    );
  }
  if (filed) return <p role="status">{filed}</p>;

  async function send() {
    setError(null);
    try {
      const accepted = await reportError({
        run_id: runId,
        item_id: itemId,
        error_type: errorType,
        note: note.trim(),
        reporter: reporter.trim(),
      });
      setFiled(`Report ${accepted.report_id}: ${accepted.status}. The board is not changed.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  const incomplete = !note.trim() || !reporter.trim();
  return (
    <form
      className="rd-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!incomplete) void send();
      }}
    >
      <label className="rd-field" htmlFor={ids.type}>
        What is wrong
        <select id={ids.type} value={errorType} onChange={(event) => setErrorType(event.target.value as ErrorType)}>
          {ERROR_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label className="rd-field" htmlFor={ids.note}>
        What you found
        <textarea id={ids.note} rows={3} value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <label className="rd-field" htmlFor={ids.name}>
        Your name (recorded with the report)
        <input id={ids.name} value={reporter} onChange={(event) => setReporter(event.target.value)} />
      </label>
      {error && (
        <p className="rd-error" role="alert">
          {error}
        </p>
      )}
      <Button
        type="submit"
        variant="secondary"
        disabledReason={incomplete ? "Say what you found and who you are." : undefined}
      >
        Send report
      </Button>
    </form>
  );
}
