// The fixed icon set (design-system.md, Iconography): 16px grid, 1.5px stroke, round caps,
// currentColor. Icons are decorative: each one sits next to a text label that carries the
// meaning, so they are hidden from assistive technology.
export type IconName =
  | "check"
  | "alert"
  | "lock"
  | "circle"
  | "dash"
  | "arrow"
  // The stage panel (issue 229): one icon per place in the app and per stage of a board.
  | "plus"
  | "history"
  | "brief"
  | "search"
  | "grid"
  | "verify"
  | "sign"
  | "export"
  | "chevrons";

const PATHS: Record<IconName, string> = {
  check: "M3.5 8.5l3 3 6-7",
  alert: "M8 2.5l6 11H2z M8 6.5v3 M8 11.75v0.01",
  lock: "M4 7.5h8v6H4z M5.75 7.5V5.5a2.25 2.25 0 0 1 4.5 0v2",
  circle: "M8 3a5 5 0 1 0 0.01 0z",
  dash: "M4 8h8",
  arrow: "M3 8h10 M9 4l4 4-4 4",
  plus: "M8 3v10 M3 8h10",
  history: "M8 3a5 5 0 1 0 0.01 0z M8 5.25V8l2 1.5",
  brief: "M3 13h2.5L13 5.5 10.5 3 3 10.5z",
  search: "M7 3a4 4 0 1 0 0.01 0z M10 10l3.5 3.5",
  grid: "M3 3h4v4H3z M9 3h4v4H9z M3 9h4v4H3z M9 9h4v4H9z",
  verify: "M4 2.5h5.5L12 5v8.5H4z M6 9l1.5 1.5 3-3",
  sign: "M2.5 10.5c2 0 2.5-5 4-5s0 5 2 5 2-2.5 3.5-2.5 1.5 2 2 2 M2.5 13.5h11",
  export: "M8 2.5V10 M5 5.5l3-3 3 3 M3.5 9.5v4h9v-4",
  chevrons: "M9 4L5 8l4 4 M13 4L9 8l4 4",
};

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className="rd-icon"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      data-icon={name}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
