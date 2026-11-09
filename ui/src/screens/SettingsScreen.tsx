// S9 Settings, the part for this browser (PRD 8A, issue 234): how Shortlist cards show
// status (ADR-026) and the appearance. Both are per-browser choices in v1 (single user,
// ADR-017), stored like the other conveniences; neither changes what the API records. The
// budget, source and provider settings in PRD S9 are not here yet.
import { useState } from "react";
import { type CardStyle, setCardStyle, storedCardStyle } from "../cardStyle";
import { type Appearance, setAppearance, storedAppearance } from "../theme";
import "./screens.css";

export function SettingsScreen() {
  const [style, setStyle] = useState<CardStyle>(storedCardStyle);
  const [appearance, setLook] = useState<Appearance>(storedAppearance);

  return (
    <section className="rd-screen rd-detail" aria-labelledby="settings-title">
      <h1 id="settings-title" className="rd-screen-title">
        Settings
      </h1>
      <fieldset className="rd-settings-group">
        <legend>Status on Shortlist cards</legend>
        <label className="rd-settings-option">
          <input
            type="radio"
            name="card-style"
            checked={style === "marks"}
            onChange={() => {
              setCardStyle("marks");
              setStyle("marks");
            }}
          />
          <span>
            <strong>Compact marks</strong> (default). ✓ verified or open, ? needs a check, a lock for permission required. The
            full wording shows on hover, in the details and in the Full view.
          </span>
        </label>
        <label className="rd-settings-option">
          <input
            type="radio"
            name="card-style"
            checked={style === "wording"}
            onChange={() => {
              setCardStyle("wording");
              setStyle("wording");
            }}
          />
          <span>
            <strong>Full wording.</strong> The fixed status wording under every image. Easier to read, more text while
            shortlisting.
          </span>
        </label>
        <p className="rd-note">Either way, every card shows both attribution and rights, and Verify always uses the full wording.</p>
      </fieldset>

      <fieldset className="rd-settings-group">
        <legend>Appearance</legend>
        {(
          [
            ["system", "Match my computer"],
            ["light", "Light"],
            ["dark", "Dark"],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className="rd-settings-option">
            <input
              type="radio"
              name="appearance"
              checked={appearance === value}
              onChange={() => {
                setAppearance(value);
                setLook(value);
              }}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      <p className="rd-note">These choices are saved in this browser.</p>
    </section>
  );
}
