// The fixed icon set (design-system.md, Iconography): 16px grid, 1.5px stroke, round caps,
// currentColor. Icons are decorative: each one sits next to a text label that carries the
// meaning, so they are hidden from assistive technology.
export type IconName = "check" | "alert" | "lock" | "circle" | "dash" | "arrow";

const PATHS: Record<IconName, string> = {
  check: "M3.5 8.5l3 3 6-7",
  alert: "M8 2.5l6 11H2z M8 6.5v3 M8 11.75v0.01",
  lock: "M4 7.5h8v6H4z M5.75 7.5V5.5a2.25 2.25 0 0 1 4.5 0v2",
  circle: "M8 3a5 5 0 1 0 0.01 0z",
  dash: "M4 8h8",
  arrow: "M3 8h10 M9 4l4 4-4 4",
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
