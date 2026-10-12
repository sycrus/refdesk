// ConfirmDialog (design/components/ConfirmDialog.md): the last step before the irreversible
// export (gates G4 and G5). The forward button stays disabled, with the reason in text,
// until the acknowledgement is ticked and "Approving as" is filled in; the API checks both
// again (ApprovalRequest), so the dialog only reflects the gate (PRD 8B).
//
// Focus: moves into the dialog on open, is trapped there (Tab and Shift+Tab wrap), and
// returns to the element that opened it on close. Escape cancels.
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { NOT_LEGAL_ADVICE } from "../generated/wording";
import { Button } from "./Button";
import "./ConfirmDialog.css";

export interface ReviewedItem {
  id: string;
  title: string;
  note: string;
}

export interface ConfirmDialogProps {
  open: boolean;
  itemCount: number;
  countsByStatus: Record<string, number>; // rights status label -> items
  reviewed: ReviewedItem[];
  excludedUnverified: number; // unverified items left out because nobody reviewed them
  runId: string;
  defaultApprover?: string;
  onConfirm: (approval: { approver: string; acknowledged: true }) => void;
  onCancel: () => void;
}

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function ConfirmDialog(props: ConfirmDialogProps) {
  if (!props.open) return null;
  return <OpenDialog {...props} />;
}

function OpenDialog({
  itemCount,
  countsByStatus,
  reviewed,
  excludedUnverified,
  runId,
  defaultApprover = "",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const dialog = useRef<HTMLDivElement>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [approver, setApprover] = useState(defaultApprover);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => opener?.focus();
  }, []);

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
      return;
    }
    if (event.key !== "Tab" || !dialog.current) return;
    const focusable = [...dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }

  const name = approver.trim();
  const reason = !acknowledged
    ? "Tick the acknowledgement to continue."
    : !name
      ? "Enter your name in Approving as."
      : undefined;
  const noun = itemCount === 1 ? "item" : "items";

  return (
    <div className="rd-dialog-backdrop">
      <div
        ref={dialog}
        className="rd-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
      >
        <h2 id={titleId} className="rd-dialog-title">
          Approve and export {itemCount} {noun}
        </h2>
        <section aria-label="By rights status">
          <ul className="rd-dialog-counts">
            {Object.entries(countsByStatus).map(([status, count]) => (
              <li key={status}>
                <span>{status}</span> <span className="rd-dialog-count">{count}</span>
              </li>
            ))}
          </ul>
          {excludedUnverified > 0 && (
            <p>
              {excludedUnverified} unverified {excludedUnverified === 1 ? "item is" : "items are"} excluded
              because {excludedUnverified === 1 ? "it was" : "they were"} not reviewed with a note.
            </p>
          )}
        </section>
        {reviewed.length > 0 && (
          <section aria-label="Items you reviewed">
            <h3 className="rd-dialog-subtitle">Items you reviewed</h3>
            <ul className="rd-dialog-reviewed">
              {reviewed.map((item) => (
                <li key={item.id}>
                  <span className="rd-dialog-id">{item.id}</span> {item.title}: {item.note}
                </li>
              ))}
            </ul>
          </section>
        )}
        <p className="rd-dialog-next">
          After export, the board becomes read-only and a receipt with run ID{" "}
          <span className="rd-dialog-id">{runId}</span> is shown. Editing needs a new version.
        </p>
        <label className="rd-dialog-field">
          <span>Approving as</span>
          <input type="text" value={approver} onChange={(event) => setApprover(event.target.value)} />
        </label>
        <label className="rd-dialog-ack">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />
          <span>{NOT_LEGAL_ADVICE}</span>
        </label>
        <div className="rd-dialog-actions">
          <Button onClick={onCancel}>Cancel</Button>
          <Button
            variant="primary"
            disabledReason={reason}
            onClick={() => onConfirm({ approver: name, acknowledged: true })}
          >
            Approve and export
          </Button>
        </div>
      </div>
    </div>
  );
}
