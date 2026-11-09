// How Shortlist cards show status (ADR-026, issue 232): compact marks by default, or the
// full fixed wording. The Full view and Verify always use the full wording, whatever this
// says. A per-browser choice (v1 is single-user), stored like the appearance in theme.ts;
// the Settings control that changes it is issue 234.
export type CardStyle = "marks" | "wording";

const KEY = "refdesk-card-style";

export function storedCardStyle(): CardStyle {
  try {
    return localStorage.getItem(KEY) === "wording" ? "wording" : "marks";
  } catch {
    return "marks";
  }
}

export function setCardStyle(style: CardStyle): void {
  try {
    if (style === "marks") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, style);
  } catch {
    // Storage blocked: the default applies.
  }
}
