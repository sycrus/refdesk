// The appearance choice (issue 228): match the computer, or force light or dark. Applied
// as data-theme on <html>; the generated tokens.css already has both themes. The choice is
// a per-browser convenience (v1 is single-user and local), so it lives in localStorage,
// wrapped in try/catch because storage can be blocked. Without it the app would always
// follow the computer, with no way to override.
export type Appearance = "system" | "light" | "dark";

const KEY = "refdesk-appearance";

export function storedAppearance(): Appearance {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function applyAppearance(appearance: Appearance, root: HTMLElement = document.documentElement): void {
  if (appearance === "system") delete root.dataset.theme;
  else root.dataset.theme = appearance;
}

export function setAppearance(appearance: Appearance): void {
  try {
    if (appearance === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, appearance);
  } catch {
    // Storage blocked: the choice still applies for this page view.
  }
  applyAppearance(appearance);
}
