// Button (design/components/Button.md). There is no bare `disabled` prop: a button can
// only be disabled by giving the reason, which is shown next to it ("Disabled buttons
// explain why in adjacent text"). It uses aria-disabled rather than `disabled`, so it
// stays focusable and a keyboard or screen-reader user can reach the reason.
import { type ReactNode, useId } from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps {
  children: ReactNode; // the label, in words
  onClick?: () => void;
  variant?: ButtonVariant;
  type?: "button" | "submit";
  disabledReason?: string; // set to disable the button; shown next to it
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  type = "button",
  disabledReason,
}: ButtonProps) {
  const reasonId = useId();
  const disabled = Boolean(disabledReason);
  return (
    <span className="rd-button-wrap">
      <button
        type={type}
        className={`rd-button rd-button--${variant}`}
        aria-disabled={disabled || undefined}
        aria-describedby={disabled ? reasonId : undefined}
        onClick={(event) => {
          if (disabled) {
            event.preventDefault();
            return;
          }
          onClick?.();
        }}
      >
        {children}
      </button>
      {disabled && (
        <span id={reasonId} className="rd-button-reason">
          {disabledReason}
        </span>
      )}
    </span>
  );
}
