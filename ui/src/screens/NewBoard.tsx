// S1 New board (PRD 8A): the brief and its constraints. Validation is the API's job
// (BoardRequest); this form sends what was typed and shows the API's message if it refuses.
// Novelty is not offered yet: the API accepts it but does not apply it (M4).
import { type FormEvent, useState } from "react";
import { ApiError, createBoard } from "../api/client";
import type { BoardRequest, Conditions, UsageMode } from "../api/types";
import { Button } from "../components/Button";
import "./screens.css";

const CONDITION_FIELDS: { key: keyof Conditions; label: string; hint: string }[] = [
  { key: "period", label: "Period", hint: "e.g. 17th century or 1650" },
  { key: "material", label: "Material", hint: "e.g. oil" },
  { key: "motif", label: "Motif", hint: "e.g. ships" },
  { key: "department", label: "Department", hint: "e.g. paintings" },
];

export function buildRequest(form: FormData): BoardRequest {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  const conditions: Conditions = {};
  for (const { key } of CONDITION_FIELDS) {
    if (text(key)) conditions[key] = text(key);
  }
  return {
    brief: text("brief"),
    usage_mode: (text("usage_mode") || "reference_only") as UsageMode,
    conditions,
    avoid: text("avoid")
      .split(",")
      .map((term) => term.trim())
      .filter(Boolean),
    anchor_id: text("anchor_id") || null,
    keep_local: form.get("keep_local") === "on",
    budget_cap_usd: Number(text("budget_cap_usd") || "0.05"),
    target_items: Number(text("target_items") || "12"),
  };
}

export function NewBoard({ onCreated }: { onCreated: (runId: string) => void }) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSending(true);
    setError(null);
    try {
      const created = await createBoard(buildRequest(new FormData(event.currentTarget)));
      onCreated(created.run_id);
    } catch (err) {
      setError(err instanceof ApiError ? `The API refused this board: ${err.message}` : `Could not reach the API: ${String(err)}`);
      setSending(false);
    }
  }

  return (
    <form className="rd-form" onSubmit={submit} aria-labelledby="new-board-title">
      <h1 id="new-board-title" className="rd-screen-title">
        New board
      </h1>
      <label className="rd-field">
        <span>Brief</span>
        <textarea name="brief" required rows={3} placeholder="What do you need references for?" />
      </label>

      <fieldset className="rd-fieldset">
        <legend>Usage</legend>
        <label>
          <input type="radio" name="usage_mode" value="reference_only" defaultChecked /> Reference only (every
          rights status shown)
        </label>
        <label>
          <input type="radio" name="usage_mode" value="reproduction" /> Reproduction (only works the source states
          are open)
        </label>
      </fieldset>

      <fieldset className="rd-fieldset rd-fieldset--grid">
        <legend>Conditions (optional)</legend>
        {CONDITION_FIELDS.map(({ key, label, hint }) => (
          <label key={key} className="rd-field">
            <span>{label}</span>
            <input type="text" name={key} placeholder={hint} />
          </label>
        ))}
      </fieldset>

      <div className="rd-form-grid">
        <label className="rd-field">
          <span>Avoid (comma-separated words or record IDs)</span>
          <input type="text" name="avoid" placeholder="e.g. red, met:436535" />
        </label>
        <label className="rd-field">
          <span>More like this work (record ID, optional)</span>
          <input type="text" name="anchor_id" placeholder="e.g. met:436535" />
        </label>
        <label className="rd-field">
          <span>Budget cap (USD)</span>
          <input type="number" name="budget_cap_usd" defaultValue="0.05" min="0.01" step="0.01" />
        </label>
        <label className="rd-field">
          <span>Items wanted</span>
          <input type="number" name="target_items" defaultValue="12" min="1" max="50" />
        </label>
      </div>

      <label className="rd-check">
        <input type="checkbox" name="keep_local" /> Keep this brief on this machine (never sent to a cloud model)
      </label>

      {error && (
        <p className="rd-error" role="alert">
          {error}
        </p>
      )}
      <div>
        <Button type="submit" variant="primary" disabledReason={sending ? "Sending the brief…" : undefined}>
          Find references
        </Button>
      </div>
    </form>
  );
}
